"""V15: faithful Café→Azul copy — detail preserved, smoothing demoted.

User intent: copy the Azul bass faithfully **without smoothing it away**.
V14's regional smooth + reliability shrink are kept as *diagnostic*
columns; they are no longer the operational deliverable.

What V15 does with the evidence we already have:

1. **Faithful curve** = pair-first raw median (no octave smooth) + energy
   neutrality only. Uncertainty stays in MAD / CI columns, not baked into
   a flattened EQ.
2. **Richer observation weights** from V4.1 that help fidelity, not smoothness:
   match-confidence, tonal proximity, relative-energy proxy, §29 phase mix.
3. **Low-λ joint fit** (less shrinkage to 0 dB) as a continuous alternative.
4. **Fidelity audit**: apply EQ+gain to Café, measure spectral error vs Azul
   in bands — prove the faithful curve copies better than the over-smoothed one.
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

from repo_paths import AUD, MANIFEST, OUT, REPO, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v11 as v11  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v14 as v14  # noqa: E402
import run_manifest  # noqa: E402

# Low regularisation: keep measurable structure (esp. presence) instead of
# shrinking unsupported bins hard toward 0.
LAMBDA_FAITHFUL = (20.0, 5.0, 20.0, 0.35)

CONF_MAP = {"high": 1.00, "medium": 0.85, "low": 0.55}
BANDS = [
    (25, 60, "25-60"),
    (60, 120, "60-120"),
    (120, 250, "120-250"),
    (250, 500, "250-500"),
    (500, 1000, "500-1k"),
    (1000, 2000, "1k-2k"),
    (2000, 4000, "2k-4k"),
    (4000, 8000, "4k-8k"),
    (8000, 12000, "8k-12k"),
]


def tonal_proximity(f: np.ndarray, f0: np.ndarray, kind: np.ndarray) -> np.ndarray:
    """Gaussian proximity to nearest harmonic (±32 cents), V4.1 §15/§25.3."""
    f = np.asarray(f, float)
    f0 = np.asarray(f0, float)
    kind = np.asarray(kind, object)
    out = np.ones(len(f), dtype=float)
    ok = np.isfinite(f) & np.isfinite(f0) & (f0 > 0)
    # Nearest harmonic index.
    h = np.clip(np.round(f[ok] / f0[ok]), 1, 32)
    target = h * f0[ok]
    cents = 1200.0 * np.log2(np.maximum(f[ok], 1e-9) / np.maximum(target, 1e-9))
    prox = np.exp(-0.5 * (cents / 32.0) ** 2)
    out[ok] = prox
    # Attack keeps a high floor (noise of the string still carries timbre).
    # We don't have phase here in all frames; kind-based floor:
    is_resid = kind == "band_residual"
    out = np.where(is_resid, 0.75 + 0.25 * out, 0.35 + 0.65 * out)
    return out


def relative_energy_score(
    snr_db: np.ndarray,
    freq: np.ndarray,
    rel_db: np.ndarray | None = None,
) -> np.ndarray:
    """V4.1 relative-energy score; prefer ``rel_db`` (event peak) when present.

    Falls back to the SNR-vs-threshold proxy used before V21.
    """
    freq = np.asarray(freq, float)
    if rel_db is not None:
        rel = np.asarray(rel_db, float)
        if np.isfinite(rel).any():
            thr = v12.relative_energy_threshold(freq)
            raw = np.clip((rel - thr) / 28.0, 0.0, 1.0)
            # Where rel_db missing, blend in SNR proxy.
            snr_thr = v12.snr_threshold(freq)
            snr_raw = np.clip((np.asarray(snr_db, float) - snr_thr) / 28.0, 0.0, 1.0)
            raw = np.where(np.isfinite(rel), raw, snr_raw)
            return np.sqrt(raw)
    thr = v12.snr_threshold(freq)
    raw = np.clip((np.asarray(snr_db, float) - thr) / 28.0, 0.0, 1.0)
    return np.sqrt(raw)


def match_confidence_table() -> pd.DataFrame:
    match = pd.read_csv(OUT / "MATCHING_EVENTOS_V10_2.csv")
    # event column in fund/ton is the matched index; map from event_cafe.
    z = match.rename(columns={"event_cafe": "event"})[
        ["pair", "event", "match_cost", "confidence"]
    ].copy()
    z["conf_weight"] = z.confidence.map(CONF_MAP).fillna(0.55)
    # Continuous cost → [0.4, 1] (lower cost = higher weight).
    z["cost_weight"] = np.clip(1.3 - 0.35 * z.match_cost, 0.4, 1.0)
    z["event_confidence"] = z.conf_weight * z.cost_weight
    return z[["pair", "event", "event_confidence"]]


def enrich_observations(gain_db: float) -> pd.DataFrame:
    """Timbre observations with V4.1-style fidelity weights (no smoothing)."""
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()

    fund = fund.copy()
    ton = ton.copy()
    fund["y_timbre"] = fund.y - gain_db
    ton["y_timbre"] = ton.y
    res["y_timbre"] = res.y
    fund["kind"] = "fundamental"
    if "kind" not in ton.columns:
        ton["kind"] = "tonal_harmonic"

    frames = []
    for df, w0 in ((fund, 1.0), (ton, 0.55), (res, 0.20)):
        z = df.copy()
        z["w0"] = z.weight_base * w0
        frames.append(z)

    obs = pd.concat(frames, ignore_index=True, sort=False)
    conf = match_confidence_table()
    obs = obs.merge(conf, on=["pair", "event"], how="left")
    obs["event_confidence"] = obs.event_confidence.fillna(0.70)

    f = obs.f.to_numpy(float)
    obs["tonal_score"] = tonal_proximity(f, obs.f0.to_numpy(float), obs.kind.to_numpy())
    rel_col = obs["rel_db"].to_numpy(float) if "rel_db" in obs.columns else None
    obs["rel_energy_score"] = relative_energy_score(obs.snr.to_numpy(float), f, rel_col)
    obs["phase_mix"] = v14._phase_mix_weight(f, obs.phase.to_numpy())
    obs["snr_score"] = np.clip((obs.snr.to_numpy(float) - v12.snr_threshold(f)) / 18.0, 0.0, 1.0)
    obs["codec_prior"] = v12.codec_prior(f)
    obs["open_mask"] = v12.open_string_mask(f, obs.family.to_numpy())
    obs["mains_factor"] = v12.mains_factor(f, obs.snr.to_numpy(float))

    # Windows → cycles. Prefer true `low` durations (~700 ms) when present.
    win = pd.read_csv(OUT / "VENTANAS_ADAPTATIVAS_V10_2.csv")
    obs = obs.merge(
        win[["pair", "event", "phase", "duration_cafe_ms"]],
        on=["pair", "event", "phase"],
        how="left",
    )
    # Body fallback 165 ms; low-phase missing rows use 400 ms nominal (conservative).
    is_low = obs.phase.to_numpy(object) == "low"
    dur_ms = obs.duration_cafe_ms.to_numpy(float)
    missing = ~np.isfinite(dur_ms)
    dur_ms = dur_ms.copy()
    dur_ms[missing & is_low] = 400.0
    dur_ms[missing & ~is_low] = 165.0
    obs["duration_s"] = dur_ms / 1000.0
    obs["cycles_score"] = v12.cycles_score(f, obs.duration_s, obs.phase)

    obs["w"] = (
        obs.w0
        * obs.snr_score
        * obs.rel_energy_score
        * obs.cycles_score
        * obs.tonal_score
        * obs.codec_prior
        * obs.open_mask
        * obs.mains_factor
        * obs.event_confidence
        * obs.phase_mix
    )
    return obs


def faithful_pair_first(obs: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Pair-first median on PAIR_F — **no** regional smoothing."""
    obs = obs[obs.w > 0].copy()
    pair_curves = {}
    for pair, g in obs.groupby("pair"):
        pair_curves[pair] = v14._local_median(
            g.f, g.y_timbre, g.w, v14.PAIR_F, sigma_oct=1.0 / 10.0
        )
    order = sorted(pair_curves)
    mat = np.vstack([pair_curves[p] for p in order])
    with np.errstate(all="ignore"):
        across = np.nanmedian(mat, axis=0)
        mad = 1.4826 * np.nanmedian(np.abs(mat - across), axis=0)
        n_pairs = np.sum(np.isfinite(mat), axis=0)

    # Attack / sustain for disagreement diagnostics only.
    att, sus = [], []
    for pair, g in obs.groupby("pair"):
        ga, gs = g[g.phase == "attack"], g[g.phase == "sustain"]
        att.append(v14._local_median(ga.f, ga.y_timbre, ga.w, v14.PAIR_F, 1 / 10))
        sus.append(v14._local_median(gs.f, gs.y_timbre, gs.w, v14.PAIR_F, 1 / 10))
    att_m = np.nanmedian(np.vstack(att), axis=0)
    sus_m = np.nanmedian(np.vstack(sus), axis=0)

    table = pd.DataFrame(
        {
            "frequency_hz": v14.PAIR_F,
            "eq_faithful_raw_db": across,
            "pair_mad_db": mad,
            "n_pairs": n_pairs,
            "attack_db": att_m,
            "sustain_db": sus_m,
            "attack_sustain_disagreement_db": np.abs(att_m - sus_m),
        }
    )
    return table, mat


def upsample_faithful(freq_src, values, freq_dst):
    ok = np.isfinite(values) & (freq_src > 0)
    return np.interp(np.log(freq_dst), np.log(freq_src[ok]), values[ok])


def band_spectrum_db(y: np.ndarray, sr: int, nperseg: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    y = y - np.mean(y)
    # Active frames only.
    n = max(int(0.02 * sr), 1)
    fr = y[: len(y) // n * n].reshape(-1, n)
    e = np.sqrt(np.mean(fr**2, axis=1))
    act = fr[e > 0.2 * e.max()].ravel() if e.max() > 0 else y
    f, P = _sig.welch(act, sr, nperseg=min(nperseg, max(256, len(act) // 4)))
    return f, 10 * np.log10(np.maximum(P, 1e-30))


def fidelity_audit(
    curve_dense: np.ndarray,
    gain_db: float,
    label: str,
    pairs: list[str] | None = None,
) -> pd.DataFrame:
    """Spectral error of Café+EQ+gain versus Azul — the real fidelity metric."""
    h = m.fir_from_curve(curve_dense)
    if pairs is None:
        # Fretted + chromatic: less nut colouring; still all from existing sessions.
        pairs = [
            "A_12",
            "B_12",
            "C_12",
            "D_12",
            "E_12",
            "G_12",
            "C_24",
            "C_chromatic",
        ]
    rows = []
    for key in pairs:
        if key not in m.PAIRS:
            continue
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        z = m.apply_eq(yc, h, gain_db)
        # Align roughly by length.
        L = min(len(z), len(ya))
        z, ya = z[:L], ya[:L]
        f, Sz = band_spectrum_db(z, m.SR)
        _, Sa = band_spectrum_db(ya, m.SR)
        # Also Café raw for baseline.
        _, Sc = band_spectrum_db(yc[:L], m.SR)
        for lo, hi, name in BANDS:
            sel = (f >= lo) & (f < hi)
            if not sel.any():
                continue
            err = float(np.mean(Sz[sel] - Sa[sel]))
            rmse = float(np.sqrt(np.mean((Sz[sel] - Sa[sel]) ** 2)))
            base = float(np.sqrt(np.mean((Sc[sel] - Sa[sel]) ** 2)))
            rows.append(
                {
                    "variant": label,
                    "pair": key,
                    "band": name,
                    "bias_db": err,
                    "rmse_db": rmse,
                    "cafe_raw_rmse_db": base,
                    "improvement_db": base - rmse,
                }
            )
    return pd.DataFrame(rows)


def summarize_fidelity(df: pd.DataFrame) -> pd.DataFrame:
    g = (
        df.groupby(["variant", "band"], as_index=False)
        .agg(
            rmse_median_db=("rmse_db", "median"),
            bias_median_db=("bias_db", "median"),
            improvement_median_db=("improvement_db", "median"),
            n_pairs=("pair", "nunique"),
        )
    )
    return g


def calibrate_presence_scale(
    curve_dense: np.ndarray,
    gain_db: float,
    pairs: list[str],
    *,
    scale_lo_hz: float = 500.0,
    scale_hi_hz: float = 8000.0,
) -> tuple[np.ndarray, float, float]:
    """Scale EQ in presence/brillo only (default 0.5–8 kHz), not air.

    V20 audit: scaling everything ≥500 Hz dragged 10–18 kHz to +3.7 dB.
    V21 limits the scale to the critical copy band; air is tapered later.
    """
    fgrid = m.DENSE_F
    base = np.asarray(curve_dense, float)
    mask = (fgrid >= scale_lo_hz) & (fgrid < scale_hi_hz)

    # Preload audio + Azul spectra once.
    cache = []
    for key in pairs:
        if key not in m.PAIRS:
            continue
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        L = min(len(yc), len(ya))
        fa, Sa = band_spectrum_db(ya[:L], m.SR)
        cache.append((yc[:L], fa, Sa))

    crit = [(500, 1000), (1000, 2000), (2000, 4000), (4000, 8000)]

    def score(scale: float) -> float:
        c = base.copy()
        c[mask] = base[mask] * scale
        h = m.fir_from_curve(c)
        rmses = []
        for yc, fa, Sa in cache:
            z = m.apply_eq(yc, h, gain_db)
            fz, Sz = band_spectrum_db(z, m.SR)
            # Interpolate Azul onto EQ spectrum grid if needed.
            Sa_i = np.interp(fz, fa, Sa)
            for lo, hi in crit:
                sel = (fz >= lo) & (fz < hi)
                if sel.any():
                    rmses.append(float(np.sqrt(np.mean((Sz[sel] - Sa_i[sel]) ** 2))))
        return float(np.median(rmses)) if rmses else 1e9

    grid = np.linspace(0.35, 1.15, 17)
    scores = [(s, score(s)) for s in grid]
    best_s, best_e = min(scores, key=lambda t: t[1])
    for s in np.linspace(best_s - 0.05, best_s + 0.05, 11):
        s = float(np.clip(s, 0.3, 1.2))
        e = score(s)
        if e < best_e:
            best_e, best_s = e, s
    out = base.copy()
    out[mask] = base[mask] * best_s
    ref = v12.cafe_reference_spectrum(fgrid)
    out_n, eff = v12.energy_neutralize(out, ref)
    return out_n, best_s, gain_db + eff


def main() -> None:
    t0 = time.time()
    run_id = f"v15_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v15", stages=["improve_v15"]
    )

    if (OUT / "RESUMEN_V12.json").exists():
        gain0 = float(
            json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
        )
    else:
        gain0 = -12.0
    print(f"1 starting gain {gain0:+.3f} dB", flush=True)

    print("2 enrich observations (match/tonal/rel/phase)", flush=True)
    obs = enrich_observations(gain0)
    obs_pos = obs[obs.w > 0]
    print(
        f"   n={len(obs)} with_weight={len(obs_pos)} "
        f"median_w={obs_pos.w.median():.4f}",
        flush=True,
    )
    obs[
        [
            "pair",
            "event",
            "phase",
            "kind",
            "f",
            "y_timbre",
            "w",
            "snr_score",
            "rel_energy_score",
            "tonal_score",
            "cycles_score",
            "event_confidence",
            "phase_mix",
            "codec_prior",
        ]
    ].to_csv(OUT / "PESOS_FIDELIDAD_V15.csv", index=False)

    print("3 faithful pair-first (NO regional smooth)", flush=True)
    faithful_tbl, pair_mat = faithful_pair_first(obs)
    ref = v12.cafe_reference_spectrum(v14.PAIR_F)
    raw = faithful_tbl.eq_faithful_raw_db.to_numpy(float)
    neutral, effect = v12.energy_neutralize(np.nan_to_num(raw, nan=0.0), ref)
    gain_faithful = gain0 + effect
    print(f"   energy effect {effect:+.3f} dB → gain_faithful {gain_faithful:+.3f} dB", flush=True)

    # Diagnostic smooth (V14) kept aside — not the deliverable.
    if (OUT / "SUAVIZADO_REGIONAL_V14.csv").exists():
        # Reuse width profile from V14 if present on same grid.
        v14c = pd.read_csv(OUT / "CURVAS_DENSAS_V14.csv")
        width = np.interp(
            np.log(v14.PAIR_F), np.log(v14c.frequency_hz), v14c.smoothing_width_octaves
        )
        smoothed = v14.apply_variable_smooth(raw, v14.PAIR_F, width)
        smooth_neutral, _ = v12.energy_neutralize(np.nan_to_num(smoothed, nan=0.0), ref)
    else:
        smooth_neutral = np.full_like(neutral, np.nan)

    curve = pd.DataFrame(
        {
            "frequency_hz": v14.PAIR_F,
            # PRIMARY deliverable — faithful, unsmoothed, energy-neutral.
            "eq_faithful_db": neutral,
            "eq_faithful_raw_db": raw,
            # Diagnostics only:
            "eq_smooth_diagnostic_db": smooth_neutral,
            "pair_mad_db": faithful_tbl.pair_mad_db,
            "n_pairs": faithful_tbl.n_pairs,
            "attack_sustain_disagreement_db": faithful_tbl.attack_sustain_disagreement_db,
            "pipeline_version": "V15.0-faithful",
        }
    )
    curve.to_csv(OUT / "CURVA_FIEL_V15.csv", index=False)

    # Dense 4096 for FIR render (detail; calibrated primary written after step 5).
    dense_faithful = upsample_faithful(v14.PAIR_F, neutral, m.DENSE_F)

    print("4 low-λ continuous fit (less shrink-to-zero)", flush=True)
    # Build fit obs with enriched weights.
    fit_df = obs_pos.copy()
    fit_df["weight_base"] = fit_df.w
    # Fundamentals need absolute y (with level); rebuild from originals.
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()
    # Merge enriched w back onto raw y observations.
    keycols = ["pair", "event", "phase", "f", "kind"]
    wmap = fit_df[keycols + ["w"]].drop_duplicates(keycols)

    def attach(df):
        z = df.merge(wmap, on=keycols, how="inner")
        z = z.rename(columns={"w": "weight_base"})
        return z

    fund2 = attach(fund.assign(kind="fundamental"))
    ton2 = attach(ton if "kind" in ton.columns else ton.assign(kind="tonal_harmonic"))
    res2 = attach(res)
    obs_fit = (
        fund2.to_dict("records") + ton2.to_dict("records") + res2.to_dict("records")
    )
    print(f"   fit observations {len(obs_fit)}", flush=True)
    beta, dfn, gain_loop, history, _pp = v11.close_gain_curve_loop(
        obs_fit, LAMBDA_FAITHFUL, fund, gain_faithful
    )
    curve_fit = m.eval_q(beta)
    ref_d = v12.cafe_reference_spectrum(m.DENSE_F)
    fit_neutral, fit_effect = v12.energy_neutralize(curve_fit, ref_d)
    gain_fit = gain_loop + fit_effect
    history.to_csv(OUT / "CONVERGENCIA_GAIN_CURVA_V15.csv", index=False)
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_faithful_fit_db": fit_neutral,
            "eq_faithful_fit_raw_db": curve_fit,
            "pipeline_version": "V15.0-faithful-fit",
        }
    ).to_csv(OUT / "CURVAS_DENSAS_V15_FIT.csv", index=False)
    print(
        f"   fit gain loop {gain_loop:+.3f} → neutral {gain_fit:+.3f} dB "
        f"iters={len(history)}",
        flush=True,
    )

    print("5 calibrate pair-first presence scale (no smooth)", flush=True)
    cal_pairs = ["A_12", "C_12", "E_12", "G_12", "C_24", "C_chromatic"]
    dense_cal, presence_scale, gain_cal = calibrate_presence_scale(
        dense_faithful, gain_faithful, cal_pairs
    )
    print(
        f"   presence_scale={presence_scale:.3f} gain_cal={gain_cal:+.3f} dB",
        flush=True,
    )
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_observed_detail_db": dense_faithful,
            "eq_faithful_db": dense_cal,
            "eq_faithful_fit_db": fit_neutral,
            "pipeline_version": "V15.0-faithful",
        }
    ).to_csv(OUT / "CURVAS_DENSAS_V15_FIEL.csv", index=False)

    # Also stamp calibrated curve onto PAIR_F export as primary.
    cal_on_pair = upsample_faithful(m.DENSE_F, dense_cal, v14.PAIR_F)
    curve["eq_observed_detail_db"] = curve["eq_faithful_db"]  # previous neutral raw
    curve["eq_faithful_db"] = cal_on_pair
    curve["presence_scale"] = presence_scale
    curve.to_csv(OUT / "CURVA_FIEL_V15.csv", index=False)

    print("6 fidelity audit (render Café+EQ vs Azul)", flush=True)
    v12c = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
    c12 = np.interp(np.log(m.DENSE_F), np.log(v12c.frequency_hz), v12c.energy_neutral_db)
    g12 = float(json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"])

    audits = []
    for label, curve_d, g in (
        ("cafe_raw_baseline", np.zeros_like(m.DENSE_F), 0.0),
        ("v12_energy_neutral", c12, g12),
        ("v15_observed_detail", dense_faithful, gain_faithful),
        ("v15_faithful_calibrated", dense_cal, gain_cal),
        ("v15_faithful_lowlam_fit", fit_neutral, gain_fit),
    ):
        if label == "cafe_raw_baseline":
            rows = []
            for key in [
                "A_12",
                "B_12",
                "C_12",
                "D_12",
                "E_12",
                "G_12",
                "C_24",
                "C_chromatic",
            ]:
                p = m.PAIRS[key]
                yc, _ = m.load(p["cafe"])
                ya, _ = m.load(p["azul"])
                L = min(len(yc), len(ya))
                f, Sc = band_spectrum_db(yc[:L], m.SR)
                _, Sa = band_spectrum_db(ya[:L], m.SR)
                for lo, hi, name in BANDS:
                    sel = (f >= lo) & (f < hi)
                    if not sel.any():
                        continue
                    rmse = float(np.sqrt(np.mean((Sc[sel] - Sa[sel]) ** 2)))
                    rows.append(
                        {
                            "variant": label,
                            "pair": key,
                            "band": name,
                            "bias_db": float(np.mean(Sc[sel] - Sa[sel])),
                            "rmse_db": rmse,
                            "cafe_raw_rmse_db": rmse,
                            "improvement_db": 0.0,
                        }
                    )
            audits.append(pd.DataFrame(rows))
        else:
            audits.append(fidelity_audit(curve_d, g, label))

    audit = pd.concat(audits, ignore_index=True)
    audit.to_csv(OUT / "FIDELIDAD_RENDER_V15.csv", index=False)
    summary_fid = summarize_fidelity(audit)
    summary_fid.to_csv(OUT / "FIDELIDAD_RENDER_RESUMEN_V15.csv", index=False)
    crit = summary_fid[summary_fid.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
    overall = (
        crit.groupby("variant")
        .rmse_median_db.median()
        .sort_values()
        .rename("critical_rmse_median_db")
        .reset_index()
    )
    overall.to_csv(OUT / "FIDELIDAD_RANKING_V15.csv", index=False)
    print(overall.round(3).to_string(index=False), flush=True)
    print(
        summary_fid[summary_fid.band == "2k-4k"][
            ["variant", "rmse_median_db", "bias_median_db", "improvement_median_db"]
        ]
        .round(2)
        .to_string(index=False),
        flush=True,
    )

    v41 = {98: -0.76, 515: 3.49, 958: 3.49, 1360: 4.08, 2630: 6.61, 4120: 6.34, 5190: 4.33}
    pts = []
    for hz, theirs in v41.items():
        pts.append(
            {
                "frequency_hz": hz,
                "v15_observed_detail_db": float(
                    np.interp(np.log(hz), np.log(m.DENSE_F), dense_faithful)
                ),
                "v15_faithful_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), dense_cal)),
                "v15_fit_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), fit_neutral)),
                "v12_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c12)),
                "v41_db": theirs,
            }
        )
    pts_df = pd.DataFrame(pts)
    pts_df.to_csv(OUT / "COMPARACION_V15_VS_V41.csv", index=False)
    print(pts_df.round(2).to_string(index=False), flush=True)

    print("7 write fidelity proof audio (C_12)", flush=True)
    proof_dir = AUD / "FIDELIDAD_V15"
    proof_dir.mkdir(parents=True, exist_ok=True)
    key = "C_12"
    p = m.PAIRS[key]
    yc, _ = m.load(p["cafe"])
    ya, _ = m.load(p["azul"])
    import soundfile as sf

    # Primary faithful = calibrated (best unsmoothed copy by render).
    h_f = m.fir_from_curve(dense_cal)
    h_fit = m.fir_from_curve(fit_neutral)
    h_12 = m.fir_from_curve(c12)
    z_f = m.apply_eq(yc, h_f, gain_cal)
    z_fit = m.apply_eq(yc, h_fit, gain_fit)
    z_12 = m.apply_eq(yc, h_12, g12)
    L = min(len(z_f), len(z_fit), len(z_12), len(ya))
    sf.write(proof_dir / "CAFE_ORIGINAL.flac", yc[:L], m.SR, subtype="PCM_24")
    sf.write(proof_dir / "AZUL_ORIGINAL.flac", ya[:L], m.SR, subtype="PCM_24")
    sf.write(proof_dir / "CAFE_V15_FIEL.flac", z_f[:L], m.SR, subtype="PCM_24")
    sf.write(proof_dir / "CAFE_V15_FIT.flac", z_fit[:L], m.SR, subtype="PCM_24")
    sf.write(proof_dir / "CAFE_V12_NEUTRAL.flac", z_12[:L], m.SR, subtype="PCM_24")
    sf.write(
        proof_dir / "ESTEREO_L_V15_FIEL_R_AZUL.flac",
        np.column_stack([z_f[:L], ya[:L]]),
        m.SR,
        subtype="PCM_24",
    )

    best = overall.iloc[0].to_dict()
    summary = {
        "run_id": run_id,
        "intent": "faithful_copy_without_smoothing",
        "primary_curve": "CURVA_FIEL_V15.csv :: eq_faithful_db",
        "primary_dense": "CURVAS_DENSAS_V15_FIEL.csv :: eq_faithful_db",
        "gain_faithful_db": gain_cal,
        "gain_observed_detail_db": gain_faithful,
        "gain_faithful_fit_db": gain_fit,
        "gain_v12_db": g12,
        "presence_scale": presence_scale,
        "energy_effect_db": effect,
        "lambda_faithful": list(LAMBDA_FAITHFUL),
        "best_fidelity_variant": best,
        "v41_presence_2k6k": pts_df[
            pts_df.frequency_hz.isin([2630, 4120, 5190])
        ].to_dict("records"),
        "note": (
            "Primary eq_faithful_db = pair-first detail scaled above 500 Hz to "
            "minimise Café→Azul render RMSE (no octave smoothing, no reliability "
            "shrink). eq_observed_detail_db keeps the unscaled pair-first shape. "
            "eq_smooth_diagnostic_db is NOT for implementation."
        ),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V15.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
