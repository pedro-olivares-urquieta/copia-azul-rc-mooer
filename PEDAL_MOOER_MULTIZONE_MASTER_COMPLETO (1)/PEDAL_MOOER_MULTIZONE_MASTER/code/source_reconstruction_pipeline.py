#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import soundfile as sf
from scipy import ndimage, signal
from scipy.optimize import differential_evolution
from scipy.signal.windows import dpss

SETUPS = {
    "bass": {"name": "Bajo", "pink": "Pink rc bass on.m4a", "sweep": "1 22k rc bass on.m4a"},
    "hybrid": {"name": "Híbrido", "pink": "Pink rc hybrid on.m4a", "sweep": "1 22k rc hybrid on.m4a"},
    "guitar": {"name": "Guitarra", "pink": "Pink rc guitar on.m4a", "sweep": "1 22k rc guitar on.m4a"},
}
PINK_REF = "Pink.m4a"
SWEEP_REF = "1 22k.m4a"
GLOBAL_GAIN_DB = 3.0
LOCKED_FREQS = np.array([30.0, 148.0, 735.0, 3637.0, 18000.0])
LOCKED_Q = 0.3
GAIN_VALUES = np.arange(-16.0, 16.0001, 0.5)
OLD_Q03 = {
    "bass": np.array([15.0, 3.5, -3.0, 15.5, -3.5]),
    "hybrid": np.array([-1.5, 3.0, 4.0, 8.5, 1.5]),
    "guitar": np.array([-10.5, 6.0, 0.5, 12.5, -1.5]),
}
REGIONS = [
    ("Subgraves", 20.0, 60.0),
    ("Graves", 60.0, 250.0),
    ("Medios", 250.0, 2000.0),
    ("Agudos / presencia", 2000.0, 8000.0),
    ("Brillo medido", 8000.0, 15500.0),
    ("Borde extrapolado", 15500.0, 18000.0),
]
KEY_FREQS = np.array([20, 30, 40, 60, 100, 148, 250, 500, 735, 1000, 2000, 3637, 8000, 12000, 15500, 18000], float)


def run_checked(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe(path: Path) -> dict:
    data = json.loads(run_checked([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,duration,bit_rate",
        "-of", "json", str(path),
    ]).stdout)["streams"][0]
    return {
        "codec": data.get("codec_name"),
        "sample_rate_hz": int(data.get("sample_rate", 0)),
        "channels": int(data.get("channels", 0)),
        "duration_s": float(data.get("duration", 0)),
        "bit_rate_bps": int(data.get("bit_rate", 0) or 0),
    }


def decode(path: Path, wav_dir: Path):
    meta = ffprobe(path)
    wav = wav_dir / f"{path.stem}.wav"
    run_checked(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-acodec", "pcm_f32le", str(wav)])
    x2, sr = sf.read(wav, always_2d=True, dtype="float64")
    x = x2.mean(axis=1)
    meta.update({
        "decoded_samples": len(x),
        "decoded_duration_s": len(x) / sr,
        "peak_dbfs": 20 * np.log10(np.max(np.abs(x)) + 1e-15),
        "rms_dbfs": 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-15),
        "stereo_correlation": float(np.corrcoef(x2[:, 0], x2[:, -1])[0, 1]) if x2.shape[1] > 1 else 1.0,
        "sha256": sha256(path),
    })
    return x, sr, meta


def rms_frames(x, sr, frame_s=0.05):
    n = max(1, int(sr * frame_s))
    count = len(x) // n
    blocks = x[:count * n].reshape(count, n)
    db = 20 * np.log10(np.sqrt(np.mean(blocks * blocks, axis=1) + 1e-30) + 1e-15)
    t = (np.arange(count) + 0.5) * n / sr
    return t, db


def stable_active_interval(x, sr):
    t, db = rms_frames(x, sr, 0.05)
    threshold = np.percentile(db, 90) - 12.0
    active = db > threshold
    active = ndimage.binary_closing(active, structure=np.ones(4, dtype=bool))
    labels, count = ndimage.label(active)
    best = None
    for label in range(1, count + 1):
        idx = np.where(labels == label)[0]
        if len(idx) and (best is None or len(idx) > len(best)):
            best = idx
    if best is None:
        raise RuntimeError("No se pudo detectar el tramo estable del ruido rosa")
    start = max(0.0, best[0] * 0.05 + 0.75)
    end = min(len(x) / sr, (best[-1] + 1) * 0.05 - 0.75)
    return start, end, threshold


def smooth_octave(arr, ppo, fwhm_oct):
    sigma = fwhm_oct * ppo / 2.355
    return ndimage.gaussian_filter1d(arr, sigma=sigma, axis=-1, mode="nearest")


def multitaper_blocks(x, sr, start, end, grid, ppo, block_s=4.0, hop_s=2.0, nw=3.5, k=6):
    n = int(block_s * sr)
    hop = int(hop_s * sr)
    starts = np.arange(int(start * sr), int(end * sr) - n + 1, hop)
    if len(starts) < 4:
        raise RuntimeError("Muy pocos bloques estables de ruido rosa")
    tapers = dpss(n, nw, Kmax=k, sym=False, norm=2)
    nfft = 1 << (n - 1).bit_length()
    f = np.fft.rfftfreq(nfft, 1 / sr)
    valid = (f >= 10) & (f <= 20000)
    lf = np.log(f[valid])
    rows = []
    for s0 in starts:
        block = x[s0:s0 + n].copy()
        block -= np.mean(block)
        power = np.zeros(nfft // 2 + 1)
        for taper in tapers:
            spec = np.fft.rfft(block * taper, n=nfft)
            power += np.abs(spec) ** 2 / sr
        power /= k
        power[1:-1] *= 2.0
        db = 10 * np.log10(power[valid] + 1e-30)
        rows.append(np.interp(np.log(grid), lf, db))
    rows = np.asarray(rows)
    rows = smooth_octave(rows, ppo, 1 / 12)
    return rows, starts / sr


def bootstrap_pink(out_blocks, ref_blocks, rng, n_boot=256):
    curve = np.median(out_blocks, axis=0) - np.median(ref_blocks, axis=0)
    boots = np.empty((n_boot, curve.size))
    for b in range(n_boot):
        oi = rng.integers(0, out_blocks.shape[0], out_blocks.shape[0])
        ri = rng.integers(0, ref_blocks.shape[0], ref_blocks.shape[0])
        boots[b] = np.median(out_blocks[oi], axis=0) - np.median(ref_blocks[ri], axis=0)
    q16, q84 = np.percentile(boots, [16, 84], axis=0)
    q025, q975 = np.percentile(boots, [2.5, 97.5], axis=0)
    unc = np.maximum(0.05, (q84 - q16) / 2)
    return curve, unc, q025, q975


def find_high_gap_centers(x, sr):
    t, db = rms_frames(x, sr, 0.01)
    sm = ndimage.gaussian_filter1d(db, 5)
    m1 = (t >= 15) & (t <= 28)
    i1 = np.where(m1)[0][np.argmin(sm[m1])]
    c1 = t[i1]
    m2 = (t >= c1 + 38) & (t <= min(t[-1], c1 + 42))
    i2 = np.where(m2)[0][np.argmin(sm[m2])]
    return float(c1), float(t[i2])


def fit_sweep_runs(x, sr):
    c1, c2 = find_high_gap_centers(x, sr)
    nper, hop = 4096, 512
    f, t, z = signal.stft(x, fs=sr, window="hann", nperseg=nper, noverlap=nper-hop, boundary=None, padded=False)
    fm = (f >= 20) & (f <= 20000)
    mag = np.abs(z[fm])
    idx = np.argmax(mag, axis=0)
    ridge = f[fm][idx]
    amp = mag[idx, np.arange(mag.shape[1])]
    adb = 20 * np.log10(amp + 1e-30)
    windows = [
        ("up1", c1 - 19.75, c1 - 0.35),
        ("down1", c1 + 0.35, c1 + 19.75),
        ("up2", c2 - 19.75, c2 - 0.35),
        ("down2", c2 + 0.35, c2 + 19.75),
    ]
    runs = []
    for label, lo, hi in windows:
        base = (t >= lo) & (t <= hi)
        threshold = np.percentile(adb[base], 20)
        use = base & (ridge >= 100) & (ridge <= 18000) & (adb > threshold)
        tt, yy = t[use], np.log(ridge[use])
        coef = np.polyfit(tt, yy, 1)
        for _ in range(6):
            residual = yy - np.polyval(coef, tt)
            center = np.median(residual)
            mad = 1.4826 * np.median(np.abs(residual - center)) + 1e-9
            keep = np.abs(residual - center) < max(0.04, 4 * mad)
            tt, yy = tt[keep], yy[keep]
            coef = np.polyfit(tt, yy, 1)
        b, a = coef
        runs.append({
            "label": label, "lo_s": lo, "hi_s": hi,
            "a": float(a), "b": float(b), "ridge_points": len(tt),
            "ridge_log_rmse": float(np.sqrt(np.mean((yy - (a + b * tt)) ** 2))),
            "estimated_low_hz": float(np.exp(a + b * lo)),
            "estimated_high_hz": float(np.exp(a + b * hi)),
        })
    return c1, c2, runs


def chirp_amplitude_curve(x, sr, run, grid):
    a, b = run["a"], run["b"]
    amp = np.full(grid.size, np.nan)
    snr = np.full(grid.size, np.nan)
    for j, f0 in enumerate(grid):
        t0 = (np.log(f0) - a) / b
        half = max(2.5 / f0, (np.log(2) / 96) / abs(b))
        half = min(half, 0.35)
        i0, i1 = max(0, int((t0 - half) * sr)), min(len(x), int((t0 + half) * sr))
        if i1 - i0 < 64:
            continue
        tt = np.arange(i0, i1) / sr
        inst_f = np.exp(a + b * tt)
        phase = 2 * np.pi / b * (inst_f - f0)
        c, s = np.cos(phase), np.sin(phase)
        w = np.hanning(len(tt))
        y = x[i0:i1]
        wc, ws = w * c, w * s
        matrix = np.array([
            [np.dot(wc, c), np.dot(wc, s), np.sum(wc)],
            [np.dot(ws, c), np.dot(ws, s), np.sum(ws)],
            [np.sum(wc), np.sum(ws), np.sum(w)],
        ])
        vector = np.array([np.dot(wc, y), np.dot(ws, y), np.dot(w, y)])
        try:
            coef = np.linalg.solve(matrix, vector)
        except np.linalg.LinAlgError:
            continue
        peak = math.hypot(coef[0], coef[1])
        sse = max(0.0, np.dot(w, y * y) - np.dot(coef, vector))
        residual_rms = math.sqrt(sse / (np.sum(w) + 1e-30))
        amp[j] = peak
        snr[j] = 20 * math.log10((peak / math.sqrt(2) + 1e-15) / (residual_rms + 1e-15))
    return amp, snr


def weighted_median(values, weights):
    values, weights = np.asarray(values), np.asarray(weights)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    v, w = values[valid], weights[valid]
    order = np.argsort(v)
    v, w = v[order], w[order]
    return float(v[np.searchsorted(np.cumsum(w), 0.5 * np.sum(w))])


def process_sweep(reference, output, sr, grid, ppo, ref_runs, out_runs, rng):
    curves, snrs = [], []
    for rr, oo in zip(ref_runs, out_runs):
        ar, srn = chirp_amplitude_curve(reference, sr, rr, grid)
        ao, son = chirp_amplitude_curve(output, sr, oo, grid)
        curves.append(20 * np.log10((ao + 1e-30) / (ar + 1e-30)))
        snrs.append(np.minimum(srn, son))
    curves, snrs = np.asarray(curves), np.asarray(snrs)
    curves = smooth_octave(curves, ppo, 1 / 24)
    preliminary = np.nanmedian(np.where(snrs >= 8, curves, np.nan), axis=0)
    normalized, offsets = [], []
    for row, srow in zip(curves, snrs):
        valid = (grid >= 30) & (grid <= 14000) & (srow >= 15) & np.isfinite(preliminary)
        offset = float(np.nanmedian(row[valid] - preliminary[valid]))
        offsets.append(offset)
        normalized.append(row - offset)
    normalized = np.asarray(normalized)
    masked = np.where(snrs >= 8, normalized, np.nan)
    shape = np.nanmedian(masked, axis=0)
    boots = np.empty((256, grid.size))
    for b in range(256):
        idx = rng.integers(0, 4, 4)
        boots[b] = np.nanmedian(masked[idx], axis=0)
    q16, q84 = np.nanpercentile(boots, [16, 84], axis=0)
    unc = np.maximum(0.04, (q84 - q16) / 2)
    median_snr = np.nanmedian(snrs, axis=0)
    return {
        "raw_runs": curves, "normalized_runs": normalized, "run_offsets_db": offsets,
        "shape_db": shape, "unc_db": unc, "median_snr_db": median_snr,
    }


def fuse_methods(grid, pink, pink_unc, sweep, sweep_unc, sweep_snr, ppo):
    reliable = (grid >= 30) & (grid <= 14000) & np.isfinite(sweep) & (sweep_snr >= 15) & (pink_unc < 0.8)
    weights = 1 / (pink_unc[reliable] ** 2 + sweep_unc[reliable] ** 2 + 0.05 ** 2)
    offset = weighted_median(pink[reliable] - sweep[reliable], weights)
    sweep_aligned = sweep + offset
    ws = np.where(np.isfinite(sweep_aligned), 1 / (sweep_unc ** 2 + 0.08 ** 2), 0.0)
    wp = np.where(np.isfinite(pink), 1 / (pink_unc ** 2 + 0.10 ** 2), 0.0)
    ws *= np.clip((sweep_snr - 5) / 15, 0, 1)
    edge_s = np.where(grid <= 15000, 1.0, np.clip((18000 - grid) / 3000, 0.05, 1.0))
    edge_p = np.where(grid <= 15500, 1.0, np.clip((18000 - grid) / 2500, 0.05, 1.0))
    ws *= edge_s
    wp *= edge_p
    # Two Huber iterations: isolated method artifacts cannot dominate.
    fused = (ws * np.nan_to_num(sweep_aligned) + wp * np.nan_to_num(pink)) / np.maximum(ws + wp, 1e-30)
    for _ in range(2):
        scale = np.sqrt(sweep_unc ** 2 + pink_unc ** 2 + 0.1 ** 2)
        rs, rp = np.abs(sweep_aligned - fused), np.abs(pink - fused)
        hs = np.minimum(1.0, 2.5 * scale / (rs + 1e-30))
        hp = np.minimum(1.0, 2.5 * scale / (rp + 1e-30))
        fused = (ws * hs * np.nan_to_num(sweep_aligned) + wp * hp * np.nan_to_num(pink)) / np.maximum(ws * hs + wp * hp, 1e-30)
    total_unc = np.sqrt(1 / np.maximum(ws + wp, 1e-30))
    precise = smooth_octave(fused, ppo, 1 / 24)
    measured = smooth_octave(precise, ppo, 1 / 12)
    fit = (grid >= 12000) & (grid <= 15500)
    coef = np.polyfit(np.log(grid[fit]), measured[fit], 2, w=np.sqrt(1 / (total_unc[fit] ** 2 + 0.1 ** 2)))
    extrapolated = np.polyval(coef, np.log(grid))
    blend = np.clip((grid - 15500) / 2500, 0, 1)
    recommended = (1 - blend) * measured + blend * extrapolated
    total_unc += np.where(grid > 15500, 0.25 + 0.75 * (grid - 15500) / 2500, 0)
    return {
        "alignment_offset_db": offset, "sweep_aligned_db": sweep_aligned,
        "fused_raw_db": fused, "precise_1_24oct_db": precise,
        "measured_1_12oct_db": measured, "recommended_analog_db": recommended,
        "uncertainty_db": total_unc,
    }


def gain_effective(g): return 0.75 * g

def q_effective(g): return LOCKED_Q * (0.569 - 0.0026 * g)


def bell_db(freq, center, gain):
    ge, qe = gain_effective(gain), q_effective(gain)
    A = 10 ** (ge / 40)
    r = freq / center
    return 10 * np.log10(((1 - r * r) ** 2 + (A * r / qe) ** 2) / ((1 - r * r) ** 2 + (r / (A * qe)) ** 2))


def build_band_bank(freq):
    bank = np.empty((5, len(GAIN_VALUES), len(freq)))
    for i, center in enumerate(LOCKED_FREQS):
        for j, gain in enumerate(GAIN_VALUES):
            bank[i, j] = bell_db(freq, center, gain)
    return bank


def response_indices(bank, idx):
    return GLOBAL_GAIN_DB + sum(bank[i, idx[i]] for i in range(5))


def coordinate_descent(bank, target, weights, start):
    idx = np.asarray(start, int).copy()
    current = response_indices(bank, idx)
    mse = float(np.average((current - target) ** 2, weights=weights))
    for _ in range(20):
        improved = False
        for i in range(5):
            base = current - bank[i, idx[i]]
            candidate = base[None, :] + bank[i]
            scores = np.average((candidate - target[None, :]) ** 2, axis=1, weights=weights)
            j = int(np.argmin(scores))
            if scores[j] < mse - 1e-14:
                idx[i], current, mse, improved = j, base + bank[i, j], float(scores[j]), True
        if not improved:
            break
    return idx, math.sqrt(mse), current


def pairwise_improve(bank, target, weights, idx, score, current):
    improved = True
    while improved:
        improved = False
        for i in range(5):
            for j in range(i + 1, 5):
                base = current - bank[i, idx[i]] - bank[j, idx[j]]
                cand = base[None, None, :] + bank[i, :, None, :] + bank[j, None, :, :]
                scores = np.average((cand - target[None, None, :]) ** 2, axis=2, weights=weights)
                ii, jj = np.unravel_index(np.argmin(scores), scores.shape)
                new_score = math.sqrt(float(scores[ii, jj]))
                if new_score < score - 1e-14:
                    idx[i], idx[j] = ii, jj
                    current = base + bank[i, ii] + bank[j, jj]
                    score, improved = new_score, True
    return idx, score, current


def optimize_preset(freq, bank, target, uncertainty, old_gains, seed):
    rng = np.random.default_rng(seed)
    objectives = {
        "full_uniform": np.ones_like(freq),
        "trusted_to_16k": np.where(freq <= 16000, 1.0, 0.0),
        "confidence_weighted": np.clip(1 / (uncertainty ** 2 + 0.15 ** 2), 0.2, 5.0),
    }
    objectives["confidence_weighted"] *= np.where(freq <= 15500, 1.0, np.clip((18000 - freq) / 2500, 0.25, 1.0))
    old_idx = np.clip(np.round((old_gains + 16) * 2).astype(int), 0, 64)
    all_candidates = []
    # Continuous full-range solution as an additional seed.
    def continuous_objective(g):
        resp = np.full_like(freq, GLOBAL_GAIN_DB)
        for fc, gg in zip(LOCKED_FREQS, g):
            resp += bell_db(freq, fc, gg)
        return np.mean((resp - target) ** 2)
    de = differential_evolution(continuous_objective, [(-16, 16)] * 5, seed=seed, popsize=20, maxiter=450, tol=1e-10, polish=True)
    de_idx = np.clip(np.round((de.x + 16) * 2).astype(int), 0, 64)
    starts = [old_idx, de_idx, np.full(5, 32, int)] + [rng.integers(0, 65, 5) for _ in range(128)]
    for objective_name, weights in objectives.items():
        best = None
        for start in starts:
            answer = coordinate_descent(bank, target, weights, start)
            if best is None or answer[1] < best[1]:
                best = answer
        best = pairwise_improve(bank, target, weights, best[0], best[1], best[2])
        all_candidates.append((objective_name, *best))
    # Include old preset explicitly and select minimum full-range RMSE among all candidates.
    all_candidates.append(("old", old_idx, float("nan"), response_indices(bank, old_idx)))
    evaluated = []
    for source, idx, _, response in all_candidates:
        err = response - target
        evaluated.append({
            "source": source, "idx": idx.copy(), "response": response,
            "rmse_full": float(np.sqrt(np.mean(err ** 2))),
            "rmse_16k": float(np.sqrt(np.mean(err[freq <= 16000] ** 2))),
            "p95_full": float(np.percentile(np.abs(err), 95)),
            "max_full": float(np.max(np.abs(err))),
            "bias_full": float(np.mean(err)),
        })
    recommended = min(evaluated, key=lambda x: (x["rmse_full"], x["rmse_16k"]))
    trusted = min(evaluated, key=lambda x: (x["rmse_16k"], x["rmse_full"]))
    return recommended, trusted, evaluated


def confidence_label(freq, unc):
    if freq > 15500: return "low"
    if unc <= 0.2: return "high"
    if unc <= 0.5: return "medium"
    return "low"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--output-dir", type=Path, default=Path("/mnt/data/PEDAL_EQ_DSP_REFINED_V2_Q03_LOCKED"))
    args = parser.parse_args()
    root = args.output_dir
    if root.exists(): shutil.rmtree(root)
    for sub in ["data", "plots", "code", "_wav"]: (root / sub).mkdir(parents=True, exist_ok=True)
    expected = [PINK_REF, SWEEP_REF] + [SETUPS[s][k] for s in SETUPS for k in ("pink", "sweep")]
    missing = [name for name in expected if not (args.input_dir / name).exists()]
    if missing: raise FileNotFoundError(missing)
    audio, qc_rows, rates = {}, [], set()
    for name in sorted(set(expected)):
        x, sr, meta = decode(args.input_dir / name, root / "_wav")
        audio[name] = x; rates.add(sr); qc_rows.append({"file": name, **meta})
    if len(rates) != 1: raise RuntimeError(f"Sample rates distintos: {rates}")
    sr = rates.pop(); ppo = 192
    grid = 20 * 2 ** (np.arange(int(np.log2(18000 / 20) * ppo) + 1) / ppo)
    grid = grid[grid <= 18000]
    rng = np.random.default_rng(20260730)

    # Pink noise analysis.
    pink_blocks, active_rows = {}, []
    for name in [PINK_REF] + [SETUPS[s]["pink"] for s in SETUPS]:
        start, end, threshold = stable_active_interval(audio[name], sr)
        blocks, starts = multitaper_blocks(audio[name], sr, start, end, grid, ppo)
        pink_blocks[name] = blocks
        active_rows.append({"file": name, "active_start_s": start, "active_end_s": end, "threshold_dbfs": threshold, "multitaper_blocks": len(blocks)})

    # Sweep mapping and repeated-pass analysis.
    sweep_runs, sweep_window_rows = {}, []
    for name in [SWEEP_REF] + [SETUPS[s]["sweep"] for s in SETUPS]:
        c1, c2, runs = fit_sweep_runs(audio[name], sr)
        sweep_runs[name] = runs
        for run in runs:
            sweep_window_rows.append({"file": name, "high_gap_1_s": c1, "high_gap_2_s": c2, **run})

    refined, method_rows, sweep_repeat_rows = {}, [], []
    old_curve_path = args.input_dir / "PEDAL_EQ_DSP_ANALYSIS/data/curvas_eq_96_puntos_por_octava.csv"
    old_curves = pd.read_csv(old_curve_path) if old_curve_path.exists() else None
    curves_df = pd.DataFrame({"frequency_hz": grid})
    for setup, info in SETUPS.items():
        pink, pink_unc, pink_lo95, pink_hi95 = bootstrap_pink(pink_blocks[info["pink"]], pink_blocks[PINK_REF], rng)
        sweep = process_sweep(audio[SWEEP_REF], audio[info["sweep"]], sr, grid, ppo, sweep_runs[SWEEP_REF], sweep_runs[info["sweep"]], rng)
        fused = fuse_methods(grid, pink, pink_unc, sweep["shape_db"], sweep["unc_db"], sweep["median_snr_db"], ppo)
        refined[setup] = {"pink": pink, "pink_unc": pink_unc, "pink_lo95": pink_lo95, "pink_hi95": pink_hi95, "sweep": sweep, **fused}
        curves_df[f"{setup}_pink_db"] = pink
        curves_df[f"{setup}_pink_uncertainty_db"] = pink_unc
        curves_df[f"{setup}_sweep_shape_db"] = sweep["shape_db"]
        curves_df[f"{setup}_sweep_aligned_db"] = fused["sweep_aligned_db"]
        curves_df[f"{setup}_sweep_uncertainty_db"] = sweep["unc_db"]
        curves_df[f"{setup}_fused_raw_db"] = fused["fused_raw_db"]
        curves_df[f"{setup}_precise_1_24oct_db"] = fused["precise_1_24oct_db"]
        curves_df[f"{setup}_measured_1_12oct_db"] = fused["measured_1_12oct_db"]
        curves_df[f"{setup}_recommended_analog_db"] = fused["recommended_analog_db"]
        curves_df[f"{setup}_uncertainty_db"] = fused["uncertainty_db"]
        curves_df[f"{setup}_confidence"] = [confidence_label(f, u) for f, u in zip(grid, fused["uncertainty_db"])]
        for i, row in enumerate(sweep["raw_runs"]):
            for f, val, snr in zip(grid, row, sweep["median_snr_db"]):
                sweep_repeat_rows.append({"setup": info["name"], "run": i + 1, "frequency_hz": f, "transfer_db": val, "median_snr_db": snr})
        common = (grid >= 30) & (grid <= 14000) & np.isfinite(fused["sweep_aligned_db"])
        diff = pink[common] - fused["sweep_aligned_db"][common]
        normalized_runs = sweep["normalized_runs"][:, common]
        center = np.nanmedian(normalized_runs, axis=0)
        dev = np.abs(normalized_runs - center)
        method_rows.append({
            "setup": info["name"],
            "sweep_to_pink_alignment_db": fused["alignment_offset_db"],
            "pink_vs_aligned_sweep_median_difference_db": float(np.nanmedian(diff)),
            "pink_vs_aligned_sweep_median_abs_difference_db": float(np.nanmedian(np.abs(diff))),
            "pink_vs_aligned_sweep_p95_abs_difference_db": float(np.nanpercentile(np.abs(diff), 95)),
            "sweep_repeat_median_abs_deviation_db": float(np.nanmedian(dev)),
            "sweep_repeat_p95_abs_deviation_db": float(np.nanpercentile(dev, 95)),
            "sweep_run_level_offsets_db": json.dumps([round(x, 5) for x in sweep["run_offsets_db"]]),
        })

    curves_df.to_csv(root / "data/refined_curves_192ppo.csv", index=False)
    pd.DataFrame(qc_rows).to_csv(root / "data/audio_qc.csv", index=False)
    pd.DataFrame(active_rows).to_csv(root / "data/pink_active_windows.csv", index=False)
    pd.DataFrame(sweep_window_rows).to_csv(root / "data/sweep_run_mapping.csv", index=False)
    pd.DataFrame(method_rows).to_csv(root / "data/method_validation.csv", index=False)
    pd.DataFrame(sweep_repeat_rows).to_csv(root / "data/sweep_repetitions_long.csv", index=False)

    # Optimize locked-frequency, Q=0.3 MOOER presets.
    bank = build_band_bank(grid)
    preset_rows, metric_rows, region_rows, key_rows, candidates_rows = [], [], [], [], []
    optimized = {}
    for n, (setup, info) in enumerate(SETUPS.items()):
        target = refined[setup]["recommended_analog_db"]
        rec, trusted, candidates = optimize_preset(grid, bank, target, refined[setup]["uncertainty_db"], OLD_Q03[setup], 9000 + n)
        optimized[setup] = {"recommended": rec, "trusted": trusted}
        for variant_name, candidate in [("recommended_full_range", rec), ("trusted_to_16k", trusted)]:
            gains = GAIN_VALUES[candidate["idx"]]
            for band, (f0, gain) in enumerate(zip(LOCKED_FREQS, gains), 1):
                preset_rows.append({
                    "setup": info["name"], "variant": variant_name, "global_gain_db": GLOBAL_GAIN_DB,
                    "band": band, "frequency_hz_locked": int(f0), "gain_display_db": gain,
                    "q_display_locked": LOCKED_Q, "gain_effective_approx_db": gain_effective(gain),
                    "q_effective_approx": q_effective(gain),
                })
            err = candidate["response"] - target
            for range_name, mask in [("20 Hz–18 kHz", np.ones_like(grid, bool)), ("20 Hz–16 kHz", grid <= 16000), ("30 Hz–18 kHz", grid >= 30)]:
                e = err[mask]
                metric_rows.append({
                    "setup": info["name"], "variant": variant_name, "range": range_name,
                    "rmse_db": np.sqrt(np.mean(e * e)), "mae_db": np.mean(np.abs(e)),
                    "p95_absolute_error_db": np.percentile(np.abs(e), 95),
                    "maximum_absolute_error_db": np.max(np.abs(e)), "mean_bias_db": np.mean(e),
                })
            for region, lo, hi in REGIONS:
                m = (grid >= lo) & (grid <= hi)
                e = err[m]
                region_rows.append({
                    "setup": info["name"], "variant": variant_name, "spectrum": region, "range_hz": f"{int(lo)}–{int(hi)}",
                    "rmse_db": np.sqrt(np.mean(e * e)), "mae_db": np.mean(np.abs(e)),
                    "p95_absolute_error_db": np.percentile(np.abs(e), 95), "maximum_absolute_error_db": np.max(np.abs(e)),
                    "mean_bias_db": np.mean(e),
                })
        for candidate in candidates:
            candidates_rows.append({"setup": info["name"], "source_objective": candidate["source"], "gains_db": json.dumps(GAIN_VALUES[candidate["idx"]].tolist()), **{k: candidate[k] for k in ["rmse_full", "rmse_16k", "p95_full", "max_full", "bias_full"]}})
        old_idx = np.clip(np.round((OLD_Q03[setup] + 16) * 2).astype(int), 0, 64)
        old_resp = response_indices(bank, old_idx)
        old_err = old_resp - target
        metric_rows.append({
            "setup": info["name"], "variant": "previous_q03_preset", "range": "20 Hz–18 kHz",
            "rmse_db": np.sqrt(np.mean(old_err ** 2)), "mae_db": np.mean(np.abs(old_err)),
            "p95_absolute_error_db": np.percentile(np.abs(old_err), 95), "maximum_absolute_error_db": np.max(np.abs(old_err)), "mean_bias_db": np.mean(old_err),
        })
        for f0 in KEY_FREQS:
            target0 = float(np.interp(np.log(f0), np.log(grid), target))
            response0 = float(np.interp(np.log(f0), np.log(grid), rec["response"]))
            key_rows.append({"setup": info["name"], "frequency_hz": int(f0), "refined_target_db": target0, "mooer_recommended_db": response0, "error_db": response0 - target0})

    presets_df = pd.DataFrame(preset_rows); metrics_df = pd.DataFrame(metric_rows)
    presets_df.to_csv(root / "data/mooer_presets_locked_q03.csv", index=False)
    metrics_df.to_csv(root / "data/mooer_optimization_metrics.csv", index=False)
    pd.DataFrame(region_rows).to_csv(root / "data/mooer_errors_by_region.csv", index=False)
    pd.DataFrame(key_rows).to_csv(root / "data/key_frequency_match.csv", index=False)
    pd.DataFrame(candidates_rows).to_csv(root / "data/optimization_candidates_audit.csv", index=False)

    # Previous target comparison.
    comparison_rows = []
    if old_curves is not None:
        old_f = old_curves["frequency_hz"].to_numpy()
        for setup, info in SETUPS.items():
            old = old_curves[f"{setup}_recommended_trusted_to_18k_db"].to_numpy()
            valid = np.isfinite(old) & (old_f >= 20) & (old_f <= 18000)
            new = np.interp(np.log(old_f[valid]), np.log(grid), refined[setup]["recommended_analog_db"])
            difference = new - old[valid]
            comparison_rows.append({
                "setup": info["name"], "rmse_difference_db": np.sqrt(np.mean(difference ** 2)),
                "median_difference_db": np.median(difference), "p95_absolute_difference_db": np.percentile(np.abs(difference), 95),
                "maximum_absolute_difference_db": np.max(np.abs(difference)),
            })
    pd.DataFrame(comparison_rows).to_csv(root / "data/refined_vs_previous_target.csv", index=False)

    # Plots.
    for setup, info in SETUPS.items():
        r = refined[setup]
        fig = plt.figure(figsize=(12, 6.5)); ax = fig.add_axes([0.09, 0.12, 0.87, 0.80])
        ax.semilogx(grid, r["pink"], label="Ruido rosa multitaper", alpha=0.8)
        ax.semilogx(grid, r["sweep_aligned_db"], label="Barridos sincronizados alineados", alpha=0.8)
        ax.semilogx(grid, r["recommended_analog_db"], linewidth=2.6, label="Curva refinada recomendada")
        lo, hi = r["recommended_analog_db"] - r["uncertainty_db"], r["recommended_analog_db"] + r["uncertainty_db"]
        ax.fill_between(grid, lo, hi, alpha=0.12, label="Incertidumbre empírica")
        ax.axvline(15500, linestyle="--", linewidth=1)
        ax.set_xlim(20, 18000); ax.set_xlabel("Frecuencia (Hz)"); ax.set_ylabel("Transferencia absoluta (dB)")
        ax.set_title(f"Curva refinada — {info['name']}"); ax.grid(True, which="both", alpha=0.35); ax.legend()
        fig.savefig(root / f"plots/refined_methods_{setup}.png", dpi=190); plt.close(fig)

        rec = optimized[setup]["recommended"]
        fig = plt.figure(figsize=(12, 6.5)); ax = fig.add_axes([0.09, 0.12, 0.87, 0.80])
        ax.semilogx(grid, r["recommended_analog_db"], linewidth=2.5, label="Objetivo DSP refinado")
        ax.semilogx(grid, rec["response"], linewidth=2.1, linestyle="--", label="MOOER bloqueado Q 0,3")
        for f0 in LOCKED_FREQS: ax.axvline(f0, linewidth=0.6, alpha=0.22)
        ax.set_xlim(20, 18000); ax.set_xlabel("Frecuencia (Hz)"); ax.set_ylabel("Transferencia absoluta (dB)")
        ax.set_title(f"Objetivo refinado vs. MOOER — {info['name']}"); ax.grid(True, which="both", alpha=0.35); ax.legend()
        fig.savefig(root / f"plots/refined_target_vs_mooer_{setup}.png", dpi=190); plt.close(fig)

        fig = plt.figure(figsize=(12, 5.5)); ax = fig.add_axes([0.09, 0.14, 0.87, 0.78])
        error = rec["response"] - r["recommended_analog_db"]
        ax.semilogx(grid, error); ax.axhline(0, linewidth=0.8); ax.axhline(0.5, linestyle="--", linewidth=0.8); ax.axhline(-0.5, linestyle="--", linewidth=0.8)
        ax.axvline(15500, linestyle="--", linewidth=1)
        ax.set_xlim(20, 18000); ax.set_xlabel("Frecuencia (Hz)"); ax.set_ylabel("Error MOOER − objetivo (dB)")
        ax.set_title(f"Error final — {info['name']}"); ax.grid(True, which="both", alpha=0.35)
        fig.savefig(root / f"plots/final_error_{setup}.png", dpi=190); plt.close(fig)

    fig = plt.figure(figsize=(12, 6.5)); ax = fig.add_axes([0.09, 0.12, 0.87, 0.80])
    for setup, info in SETUPS.items(): ax.semilogx(grid, refined[setup]["recommended_analog_db"], linewidth=2.2, label=info["name"])
    ax.axvline(15500, linestyle="--", linewidth=1); ax.set_xlim(20, 18000); ax.set_xlabel("Frecuencia (Hz)"); ax.set_ylabel("Transferencia absoluta (dB)")
    ax.set_title("Curvas del pedal reconstruidas — análisis refinado"); ax.grid(True, which="both", alpha=0.35); ax.legend()
    fig.savefig(root / "plots/refined_curves_combined.png", dpi=190); plt.close(fig)

    # Machine-readable JSON.
    result_json = {
        "analysis_version": "2.0.0-refined",
        "sample_rate_hz": sr, "points_per_octave": ppo,
        "trusted_measured_limit_hz": 15500, "recommended_output_limit_hz": 18000,
        "mooer_constraints": {"global_gain_db": GLOBAL_GAIN_DB, "frequencies_hz": LOCKED_FREQS.astype(int).tolist(), "q_display": LOCKED_Q},
        "setups": {},
    }
    for setup, info in SETUPS.items():
        rec, trusted = optimized[setup]["recommended"], optimized[setup]["trusted"]
        result_json["setups"][setup] = {
            "display_name": info["name"], "sweep_to_pink_alignment_db": refined[setup]["alignment_offset_db"],
            "recommended_gains_db": GAIN_VALUES[rec["idx"]].tolist(),
            "trusted_to_16k_gains_db": GAIN_VALUES[trusted["idx"]].tolist(),
            "recommended_metrics": {k: rec[k] for k in ["rmse_full", "rmse_16k", "p95_full", "max_full", "bias_full"]},
        }
    (root / "data/results_summary.json").write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # Reproducible code: copy this running script.
    shutil.copy2(Path(__file__), root / "code/refined_pedal_analysis_and_mooer_optimization.py")

    primary_metrics = metrics_df[(metrics_df["variant"] == "recommended_full_range") & (metrics_df["range"] == "20 Hz–18 kHz")].set_index("setup")
    old_metrics = metrics_df[(metrics_df["variant"] == "previous_q03_preset") & (metrics_df["range"] == "20 Hz–18 kHz")].set_index("setup")
    method_df = pd.DataFrame(method_rows).set_index("setup")
    report = [
        "# Análisis DSP refinado del pedal y nueva optimización MOOER", "",
        "## Resultado principal", "",
        "Se reconstruyeron las tres funciones de transferencia directamente desde los ocho audios originales. El nuevo pipeline no reutiliza las curvas antiguas como entrada.", "",
        "El barrido contiene cuatro mediciones independientes: dos ascendentes y dos descendentes. Cada pasada fue calibrada mediante su cresta tiempo–frecuencia y medida con demodulación síncrona de chirp. El ruido rosa se procesó por bloques con estimación multitaper DPSS y bootstrap.", "",
        "La forma del barrido y la del ruido rosa coinciden muy bien después de retirar un pequeño desplazamiento global de sesión/nivel. Por eso la curva recomendada usa el barrido para la forma de alta resolución y el ruido rosa para anclar la ganancia absoluta.", "",
        "## Desplazamiento global detectado entre estímulos", "",
        "| Setup | Corrección aplicada al barrido | Diferencia mediana absoluta rosa vs barrido | P95 |",
        "|---|---:|---:|---:|",
    ]
    for setup in SETUPS.values():
        name = setup["name"]; row = method_df.loc[name]
        report.append(f"| {name} | {row['sweep_to_pink_alignment_db']:+.3f} dB | {row['pink_vs_aligned_sweep_median_abs_difference_db']:.3f} dB | {row['pink_vs_aligned_sweep_p95_abs_difference_db']:.3f} dB |")
    report += ["", "Esta corrección es prácticamente plana con la frecuencia, por lo que se interpreta como cambio de nivel entre tomas o dependencia leve con el nivel del estímulo, no como una diferencia de EQ.", "", "## Presets MOOER finales", ""]
    for setup_key, info in SETUPS.items():
        rec = optimized[setup_key]["recommended"]; gains = GAIN_VALUES[rec["idx"]]
        report += [f"### {info['name']} — global +3 dB", "", "| Frecuencia | Gain | Q |", "|---:|---:|---:|"]
        for f0, gain in zip(LOCKED_FREQS, gains): report.append(f"| {int(f0)} Hz | {gain:+.1f} dB | 0,3 |")
        row, old = primary_metrics.loc[info["name"]], old_metrics.loc[info["name"]]
        report += ["", f"- RMSE refinado: **{row['rmse_db']:.3f} dB**.", f"- Error P95: **{row['p95_absolute_error_db']:.3f} dB**.", f"- Error máximo: **{row['maximum_absolute_error_db']:.3f} dB**.", f"- Preset anterior evaluado contra la nueva curva: {old['rmse_db']:.3f} dB RMSE.", ""]
    report += [
        "## Qué cambió respecto del primer análisis", "",
        "- Resolución duplicada: **192 puntos por octava**.",
        "- Cuatro barridos tratados por separado, incluyendo dirección ascendente/descendente.",
        "- Demodulación síncrona en vez de depender únicamente de la razón de PSD global.",
        "- Ruido rosa multitaper por bloques, con bootstrap para incertidumbre.",
        "- Separación explícita entre forma espectral y desplazamientos globales de nivel.",
        "- Fusión robusta con rechazo de discrepancias y penalización del borde AAC.",
        "- Sobre 15,5 kHz la curva recomendada se extrapola suavemente para no copiar el filtro del códec como si fuera EQ del pedal.",
        "- La optimización discreta del MOOER usa pasos reales de 0,5 dB, múltiples arranques, descenso coordenado y mejora exacta por pares de bandas.", "",
        "## Límites", "",
        "El rango principal medido con alta confianza es 20 Hz–15,5 kHz. Entre 15,5 y 18 kHz la respuesta es una continuación analógica regularizada y su confianza es baja. No existe información válida sobre 22,05–30 kHz debido a Nyquist.", "",
        "La captura no es simultánea de entrada y salida; por ello el resultado es una función de transferencia de magnitud. No se afirma una respuesta de fase, latencia ni impulso exacta.", "",
        "## Archivos principales", "",
        "- `data/refined_curves_192ppo.csv`: curvas rosa, barrido, fusión, recomendada e incertidumbre.",
        "- `data/mooer_presets_locked_q03.csv`: presets finales y variante optimizada hasta 16 kHz.",
        "- `data/mooer_optimization_metrics.csv`: auditoría de error.",
        "- `data/method_validation.csv`: acuerdo entre métodos y repeticiones.",
        "- `plots/`: validación visual y error final.",
        "- `code/refined_pedal_analysis_and_mooer_optimization.py`: pipeline completo reproducible.",
    ]
    (root / "INFORME_REFINADO.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (root / "README.md").write_text("# PEDAL EQ DSP REFINED V2\n\nAbrir primero `INFORME_REFINADO.md`.\n\nLa curva objetivo principal es `recommended_analog_db`; los presets conservan global +3 dB, frecuencias 30/148/735/3637/18000 Hz y Q 0,3.\n", encoding="utf-8")
    shutil.rmtree(root / "_wav")
    zip_path = root.with_suffix(".zip")
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file(): zf.write(path, arcname=root.name + "/" + str(path.relative_to(root)))
    print(presets_df[presets_df["variant"] == "recommended_full_range"].to_string(index=False))
    print("\n", primary_metrics[["rmse_db", "p95_absolute_error_db", "maximum_absolute_error_db"]].to_string())
    print(f"\nZIP: {zip_path}")

if __name__ == "__main__": main()
