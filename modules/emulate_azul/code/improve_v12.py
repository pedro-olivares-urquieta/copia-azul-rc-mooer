"""V12: adopts the evidence-weighting ideas that the V4.1 methodology got right.

Reviewed against our own code first, so only genuinely missing pieces are added.
Already present in V10.2 and left alone: noise-power subtraction with SNR
computed from the *unsubtracted* ratio (`build_v10_2.py:252,261`), DPSS
multitaper, F0 refinement actually wired into the fit, and string/register/phase
offsets estimated jointly rather than assumed as heuristic multipliers.

New here:

1. Energy-neutral normalisation instead of an unweighted mean anchor. V10.2
   pins the plain mean of Q(f) over 30-2500 Hz to zero, which forbids a broad
   mid-band lift by construction. Weighting the constraint by a Café reference
   spectrum is the convention that actually preserves loudness when level and
   timbre are reported separately, and it accounts for ~4.0 dB of the ~6 dB gap
   against the V4.1 curve in the presence region.
2. Kish effective sample size per frequency. `effective_pairs` only counted
   distinct pairs, so it could not tell four balanced pairs from four where one
   carries the weight.
3. Graded AAC codec prior instead of a hard 15 kHz cutoff.
4. Cycles-of-the-period support weight, joined from the window table.
5. Region-dependent SNR thresholds instead of one threshold per observation kind.
6. Mains-hum de-weighting near 50/100/150 Hz when the local SNR is weak.
7. Smooth open-string roll-off 280-300 Hz instead of a hard cut at 300 Hz.
8. Continuous reliability shrinkage toward 0 dB, replacing a binary mask.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy import signal as _sig

from repo_paths import AUDIO, OUT, CODE, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(CODE))

import build_v10_2 as m  # noqa: E402
import improve_v11 as v11  # noqa: E402
import run_config  # noqa: E402
import run_manifest  # noqa: E402

# Minimum SNR per spectral region, in dB. Mids are cheapest because they carry
# the most energy and repeat best; the top end is dearest because low-energy
# noise there is easy to mistake for brightness.
SNR_THRESHOLDS = [
    (25, 120, 10.0),
    (120, 350, 9.0),
    (350, 2500, 8.0),
    (2500, 6000, 10.0),
    (6000, 10000, 12.0),
    (10000, 18000, 14.0),
]

# How much an AAC file at ~100 kbps can still be trusted per band.
CODEC_PRIOR = [
    (0, 8000, 1.00),
    (8000, 10000, 0.92),
    (10000, 12000, 0.72),
    (12000, 15000, 0.45),
    (15000, 17000, 0.20),
    (17000, 1e9, 0.08),
]

MAINS_HZ = (50.0, 100.0, 150.0)
MAINS_SIGMA_CENTS = 40.0
MAINS_PENALTY = 0.72
MAINS_SNR_LIMIT_DB = 18.0

OPEN_FULL_HZ = 280.0
OPEN_ZERO_HZ = 300.0


def _piecewise(freq: np.ndarray, table, default: float) -> np.ndarray:
    out = np.full(len(freq), default, dtype=float)
    for lo, hi, val in table:
        out[(freq >= lo) & (freq < hi)] = val
    return out


def snr_threshold(freq: np.ndarray) -> np.ndarray:
    return _piecewise(freq, SNR_THRESHOLDS, 14.0)


def codec_prior(freq: np.ndarray) -> np.ndarray:
    return _piecewise(freq, CODEC_PRIOR, 0.08)


def mains_factor(freq: np.ndarray, snr_db: np.ndarray) -> np.ndarray:
    """De-weight bins sitting on mains harmonics only when support is weak.

    50 and 100 Hz can also be real musical content, so the penalty is
    conditional rather than a notch.
    """
    freq = np.asarray(freq, dtype=float)
    proximity = np.zeros(len(freq))
    for f0 in MAINS_HZ:
        cents = 1200.0 * np.log2(np.maximum(freq, 1e-6) / f0)
        proximity = np.maximum(proximity, np.exp(-0.5 * (cents / MAINS_SIGMA_CENTS) ** 2))
    weak = np.asarray(snr_db, dtype=float) < MAINS_SNR_LIMIT_DB
    return np.where(weak, 1.0 - proximity * (1.0 - MAINS_PENALTY), 1.0)


def open_string_mask(freq: np.ndarray, family: np.ndarray) -> np.ndarray:
    """Roll open-string evidence off between 280 and 300 Hz instead of cutting."""
    freq = np.asarray(freq, dtype=float)
    ramp = np.clip((OPEN_ZERO_HZ - freq) / (OPEN_ZERO_HZ - OPEN_FULL_HZ), 0.0, 1.0)
    is_open = np.asarray(family, dtype=object) == "open"
    return np.where(is_open, ramp, 1.0)


def cycles_score(freq: np.ndarray, duration_s: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Confidence from how many periods fit in the analysis window.

    This is why adding grid points does not improve the sub-bass: at 30 Hz a
    165 ms window holds ~5 cycles no matter how finely the axis is sampled.
    """
    cycles = np.asarray(freq, dtype=float) * np.asarray(duration_s, dtype=float)
    is_attack = np.asarray(phase, dtype=object) == "attack"
    tonal = np.clip((cycles - 4.0) / 8.0, 0.0, 1.0)
    attack = np.clip((cycles - 2.0) / 5.0, 0.0, 1.0)
    return np.where(is_attack, attack, tonal)


def effective_n(weights: np.ndarray) -> float:
    """Kish effective sample size: (sum w)^2 / sum w^2."""
    w = np.asarray(weights, dtype=float)
    s2 = float(np.sum(w) ** 2)
    ss = float(np.sum(w * w))
    return s2 / ss if ss > 0 else 0.0


def reweight_observations(obs: list[dict], windows: pd.DataFrame) -> pd.DataFrame:
    """Apply the new evidence weights on top of the existing `weight_base`."""
    df = pd.DataFrame(obs)
    win = windows[["pair", "event", "phase", "duration_cafe_ms"]].copy()
    df = df.merge(win, on=["pair", "event", "phase"], how="left")
    # Fall back to the nominal body window when the join misses.
    df["duration_s"] = df.duration_cafe_ms.fillna(165.0) / 1000.0

    thr = snr_threshold(df.f.to_numpy(float))
    df["snr_threshold_db"] = thr
    df["snr_score"] = np.clip((df.snr.to_numpy(float) - thr) / 18.0, 0.0, 1.0)
    df["cycles_score"] = cycles_score(df.f, df.duration_s, df.phase)
    df["codec_prior"] = codec_prior(df.f.to_numpy(float))
    df["mains_factor"] = mains_factor(df.f, df.snr)
    df["open_mask"] = open_string_mask(df.f, df.family)

    df["weight_base_v12"] = (
        df.weight_base.to_numpy(float)
        * df.snr_score
        * df.cycles_score
        * df.codec_prior
        * df.mains_factor
        * df.open_mask
    )
    return df


def cafe_reference_spectrum(freq: np.ndarray) -> np.ndarray:
    """Power spectrum of the Café takes, used to weight energy neutrality.

    Built from fretted notes only: open strings carry the bronze-nut colouring
    that the open-string mask already discounts.
    """
    files = sorted(p for p in AUDIO.glob("cafe__note_*_fret_*.m4a"))
    if not files:
        files = sorted(AUDIO.glob("cafe__*.m4a"))
    acc = None
    grid = np.asarray(freq, dtype=float)
    for path in files:
        y, _sr = m.load(path)
        y = y - np.mean(y)
        n = int(0.05 * m.SR)
        frames = y[: len(y) // n * n].reshape(-1, n)
        energy = np.sqrt(np.mean(frames**2, axis=1))
        active = frames[energy > 0.25 * energy.max()]
        if not len(active):
            continue
        f, P = _sig.welch(active.ravel(), m.SR, nperseg=8192)
        Pi = np.interp(grid, f, P)
        acc = Pi if acc is None else acc + Pi
    if acc is None:
        raise RuntimeError("No Café audio available for the reference spectrum")
    return acc / len(files)


def energy_effect_db(curve_db: np.ndarray, reference_power: np.ndarray) -> float:
    """Net level change the curve would cause on the reference spectrum."""
    num = float(np.sum(reference_power * 10 ** (np.asarray(curve_db, float) / 10.0)))
    den = float(np.sum(reference_power))
    return 10.0 * np.log10(num / den)


def energy_neutralize(curve_db: np.ndarray, reference_power: np.ndarray) -> tuple[np.ndarray, float]:
    """Shift the curve so it adds no net energy; return the shift as gain."""
    effect = energy_effect_db(curve_db, reference_power)
    return np.asarray(curve_db, float) - effect, effect


def frequency_effective_pairs(dfn: pd.DataFrame, freq: np.ndarray) -> pd.DataFrame:
    """Per-frequency support: pair count plus Kish effective pair count."""
    rows = []
    f_obs = dfn.f.to_numpy(float)
    for fc in freq:
        sel = np.abs(np.log2(np.maximum(f_obs, 1e-9) / fc)) <= 1.0 / 12.0
        sub = dfn[sel]
        if not len(sub):
            rows.append((0, 0.0, np.nan))
            continue
        per_pair = sub.groupby("pair").w.sum()
        rows.append((int(len(per_pair)), effective_n(per_pair.to_numpy(float)), float(sub.snr.median())))
    return pd.DataFrame(rows, columns=["pair_count", "effective_pairs_kish", "median_snr_db"])


def reliability(support: pd.DataFrame, freq: np.ndarray, ci_width: np.ndarray) -> pd.DataFrame:
    """Weighted geometric mean of the evidence factors, in [0, 1].

    Geometric so that one collapsed factor cannot be hidden by the others.
    """
    pc = support.pair_count.to_numpy(float)
    eff = support.effective_pairs_kish.to_numpy(float)
    snr = support.median_snr_db.to_numpy(float)
    thr = snr_threshold(freq)

    support_score = np.clip((pc - 1.5) / 6.5, 0.0, 1.0)
    effective_score = np.clip((eff - 1.5) / 5.5, 0.0, 1.0)
    snr_score = np.clip((np.nan_to_num(snr, nan=0.0) - thr) / 20.0, 0.0, 1.0)
    bootstrap_score = np.exp(-np.asarray(ci_width, float) / 6.0)

    eps = 1e-6
    base = (
        np.maximum(support_score, eps) ** 0.30
        * np.maximum(effective_score, eps) ** 0.22
        * np.maximum(snr_score, eps) ** 0.26
        * np.maximum(bootstrap_score, eps) ** 0.22
    )
    rel = base * codec_prior(freq)

    # Smooth roughly 1/12 octave so reliability has no seams.
    ln = np.log(freq)
    sigma = np.log(2) / 12.0
    out = np.empty_like(rel)
    for i in range(len(freq)):
        w = np.exp(-0.5 * ((ln - ln[i]) / sigma) ** 2)
        w[np.abs(ln - ln[i]) > 4 * sigma] = 0.0
        out[i] = float(np.sum(w * rel) / np.sum(w))

    return pd.DataFrame(
        {
            "frequency_hz": freq,
            "support_score": support_score,
            "effective_score": effective_score,
            "snr_score": snr_score,
            "bootstrap_score": bootstrap_score,
            "codec_prior": codec_prior(freq),
            "reliability": out,
        }
    )


def shrink_to_reliability(curve_db: np.ndarray, rel: np.ndarray, reference_power: np.ndarray):
    """Contract the curve toward 0 dB where evidence is weak, staying neutral.

    The additive constant is solved for so the shrunk curve is still
    energy-neutral, otherwise shrinkage would quietly change the level.
    """
    curve_db = np.asarray(curve_db, float)
    rel = np.asarray(rel, float)

    def neutral_error(c: float) -> float:
        return energy_effect_db((curve_db + c) * rel, reference_power)

    lo, hi = -12.0, 12.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if neutral_error(mid) > 0:
            hi = mid
        else:
            lo = mid
    c = 0.5 * (lo + hi)
    return (curve_db + c) * rel, float(c)


def main() -> None:
    t0 = time.time()
    run_id = f"v12_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(run_id, pipeline="emulate_azul_v12", stages=["improve_v12"])

    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()
    res["weight_base"] *= 0.35
    obs_raw = fund.to_dict("records") + ton.to_dict("records") + res.to_dict("records")
    windows = pd.read_csv(OUT / "VENTANAS_ADAPTATIVAS_V10_2.csv")
    print(f"1 observations {len(obs_raw)}", flush=True)

    print("2 reweighting evidence", flush=True)
    rw = reweight_observations(obs_raw, windows)
    diag = {
        "median_snr_score": float(rw.snr_score.median()),
        "median_cycles_score": float(rw.cycles_score.median()),
        "observations_zeroed_by_cycles": int((rw.cycles_score <= 0.0).sum()),
        "observations_zeroed_by_open_mask": int((rw.open_mask <= 0.0).sum()),
        "observations_hit_by_mains": int((rw.mains_factor < 1.0).sum()),
        "median_codec_prior": float(rw.codec_prior.median()),
        "weight_retained_fraction": float(
            rw.weight_base_v12.sum() / max(rw.weight_base.sum(), 1e-12)
        ),
    }
    print(json.dumps(diag, indent=2), flush=True)
    rw.to_csv(OUT / "PESOS_EVIDENCIA_V12.csv", index=False)

    obs = rw.drop(columns=["weight_base"]).rename(columns={"weight_base_v12": "weight_base"})
    obs = obs[obs.weight_base > 0].to_dict("records")
    print(f"   observaciones con peso > 0: {len(obs)} de {len(obs_raw)}", flush=True)

    lc, lr, _ = run_config.lambdas()
    if lc is None:
        lc, lr, _cv, _agg = m.cross_validate(obs)

    gain_v11 = float(json.loads((OUT / "RESUMEN_V11.json").read_text())["gain_v11_db"])
    print("3 closing gain/curve loop with new weights", flush=True)
    beta, dfn, gain, history, _pp = v11.close_gain_curve_loop(obs, lc, fund, gain_v11)
    print(history.to_string(index=False), flush=True)
    beta_r, _, _ = v11.fit_with_fixed_gain(obs, lr, gain)
    boot, _bg, _bo = m.bootstrap(obs, lc, 120)
    central, robust, safe, param, no_sub, no_high, lo, hi, _supp, cut, centers, Qs, gains = (
        m.make_variants(beta, beta_r, boot, dfn)
    )

    print("4 energy-neutral normalisation", flush=True)
    ref = cafe_reference_spectrum(m.DENSE_F)
    neutral, effect = energy_neutralize(central, ref)
    old_mean = float(central[(m.DENSE_F >= 30) & (m.DENSE_F <= 2500)].mean())
    print(f"   mean 30-2500 Hz before {old_mean:+.3f} dB", flush=True)
    print(f"   energy effect of curve {effect:+.3f} dB -> moved into the gain", flush=True)
    gain_neutral = gain + effect

    print("5 support and reliability", flush=True)
    support = frequency_effective_pairs(dfn, m.DENSE_F)
    rel = reliability(support, m.DENSE_F, hi - lo)
    recommended, const = shrink_to_reliability(neutral, rel.reliability.to_numpy(), ref)
    print(f"   reliability median {rel.reliability.median():.3f}", flush=True)
    print(f"   neutrality constant {const:+.3f} dB", flush=True)

    curve = pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "diagnostic_db": central,
            "energy_neutral_db": neutral,
            "recommended_db": recommended,
            "ci95_low_db": lo,
            "ci95_high_db": hi,
            "pair_count": support.pair_count,
            "effective_pairs_kish": support.effective_pairs_kish,
            "median_snr_db": support.median_snr_db,
            "reliability": rel.reliability,
            "codec_prior": rel.codec_prior,
            "pipeline_version": "V12.0",
        }
    )
    curve.to_csv(OUT / "CURVAS_DENSAS_V12.csv", index=False)
    rel.to_csv(OUT / "FIABILIDAD_V12.csv", index=False)

    print("6 comparison", flush=True)
    v11c = pd.read_csv(OUT / "CURVAS_DENSAS_V11.csv")
    c11 = np.interp(np.log(m.DENSE_F), np.log(v11c.frequency_hz), v11c.precise_central_db)
    # Six points the V4.1 report publishes, for an external cross-check.
    v41 = {515: 3.49, 958: 3.49, 1360: 4.08, 2630: 6.61, 4120: 6.34, 5190: 4.33}
    rows = []
    for hz, theirs in v41.items():
        rows.append(
            {
                "frequency_hz": hz,
                "v11_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c11)),
                "v12_neutral_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), neutral)),
                "v12_recommended_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), recommended)),
                "v41_reported_db": theirs,
            }
        )
    cross = pd.DataFrame(rows)
    cross["v12_neutral_minus_v41"] = cross.v12_neutral_db - cross.v41_reported_db
    cross.to_csv(OUT / "COMPARACION_V12_VS_V41.csv", index=False)
    print(cross.round(2).to_string(index=False), flush=True)

    summary = {
        "run_id": run_id,
        "gain_v11_db": gain_v11,
        "gain_v12_loop_db": gain,
        "curve_energy_effect_db": effect,
        "gain_v12_energy_neutral_db": gain_neutral,
        "mean_30_2500_before_db": old_mean,
        "mean_30_2500_after_db": float(neutral[(m.DENSE_F >= 30) & (m.DENSE_F <= 2500)].mean()),
        "diagnostic_max_db": float(central.max()),
        "neutral_max_db": float(neutral.max()),
        "recommended_max_db": float(recommended.max()),
        "reliability_median": float(rel.reliability.median()),
        "neutrality_constant_db": const,
        "weights": diag,
        "loop_iterations": int(len(history)),
        "v41_cross_check_rmse_db": float(np.sqrt(np.mean(cross.v12_neutral_minus_v41**2))),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V12.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
