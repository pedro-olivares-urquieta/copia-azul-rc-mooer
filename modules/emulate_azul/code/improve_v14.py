"""V14: map V4.1 ultraprofound methodology into post-process improvements.

Runs on existing V10.2/V12/V13 artifacts. Does not rewrite extraction.

Adoptions (without regressing what we already do better):

1. Pair-first aggregation — median within pair, then across pairs.
2. Attack–sustain disagreement → reliability factor.
3. Regional held-out smoothing widths with 0.08 dB parsimony.
4. Frequency-dependent phase mix (attack↑ highs, sustain/body↑ mids).
5. Recalibrated geometric reliability (knees fit to our N_eff≈1.26).
6. Gain restricted to non-open sustain (V4.1 §44), as an extra estimator.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import OUT, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v11 as v11  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v13 as v13  # noqa: E402
import run_config  # noqa: E402
import run_manifest  # noqa: E402

# Coarser analytic grid for pair-level work (still denser than V4.1's 912).
PAIR_F = np.geomspace(25, 18000, 768)
KERNEL_SIGMA_OCT = 1.0 / 8.0

# V4.1 §29 regional mix, mapped onto our phases.
# low-window role → body (long tonal window); sustain/attack keep their names.
# Columns: attack, stabilization, body, sustain, decay — sum = 1.
# Columns: attack, stabilization, body, sustain, decay, low — sum = 1.
# V21: V4.1 `low` window carries the 82%/38% sub-bass/bass mass (not short body).
PHASE_MIX = [
    (0, 120, 0.02, 0.00, 0.00, 0.16, 0.00, 0.82),
    (120, 350, 0.10, 0.00, 0.00, 0.52, 0.00, 0.38),
    (350, 600, 0.18, 0.00, 0.08, 0.74, 0.00, 0.00),
    (600, 900, 0.26, 0.00, 0.00, 0.74, 0.00, 0.00),
    (900, 2500, 0.26, 0.00, 0.00, 0.74, 0.00, 0.00),
    (2500, 6000, 0.40, 0.00, 0.00, 0.60, 0.00, 0.00),
    (6000, 10000, 0.64, 0.00, 0.00, 0.36, 0.00, 0.00),
    (10000, 1e9, 0.80, 0.00, 0.00, 0.20, 0.00, 0.00),
]

# Candidate smoothing widths (octaves) per region — V4.1 §33.
SMOOTH_CANDIDATES = [
    (25, 120, [1 / 5, 1 / 4, 1 / 3, 1 / 2], "subgrave"),
    (120, 350, [1 / 10, 1 / 8, 1 / 6, 1 / 4], "grave"),
    (350, 900, [1 / 12, 1 / 10, 1 / 8, 1 / 6], "medio_bajo"),
    (900, 2500, [1 / 16, 1 / 12, 1 / 10, 1 / 8], "medio"),
    (2500, 6000, [1 / 12, 1 / 10, 1 / 8, 1 / 6], "presencia"),
    (6000, 10000, [1 / 8, 1 / 6, 1 / 4, 1 / 3], "agudo"),
    (10000, 18000, [1 / 6, 1 / 4, 1 / 3, 1 / 2], "aire"),
]
PARSIMONY_DB = 0.08


def _phase_mix_weight(freq: np.ndarray, phase: np.ndarray) -> np.ndarray:
    f = np.asarray(freq, float)
    ph = np.asarray(phase, object)
    phase_idx = {
        "attack": 0,
        "stabilization": 1,
        "body": 2,
        "sustain": 3,
        "decay": 4,
        "low": 5,
    }
    has_low = bool(np.any(ph == "low"))
    out = np.ones(len(f), dtype=float)
    for lo, hi, *weights in PHASE_MIX:
        sel = (f >= lo) & (f < hi)
        if not sel.any():
            continue
        wtab = np.asarray(weights, float)
        # Legacy tables without a `low` column.
        if len(wtab) < 6:
            wtab = np.r_[wtab, 0.0]
        wtab = wtab / max(wtab.sum(), 1e-12)
        for name, i in phase_idx.items():
            msk = sel & (ph == name)
            out[msk] = wtab[i]
        # Pre-V21 CSVs: map V4.1 low mass onto body when `low` phase is absent.
        if (not has_low) and wtab[5] > 0:
            out[sel & (ph == "body")] = wtab[5] + wtab[2]
    return out


def _local_median(f_obs, y_obs, w_obs, grid, sigma_oct=KERNEL_SIGMA_OCT):
    f_obs = np.asarray(f_obs, float)
    y_obs = np.asarray(y_obs, float)
    w_obs = np.asarray(w_obs, float)
    ok = np.isfinite(f_obs) & np.isfinite(y_obs) & np.isfinite(w_obs) & (w_obs > 0) & (f_obs > 0)
    f_obs, y_obs, w_obs = f_obs[ok], y_obs[ok], w_obs[ok]
    out = np.full(len(grid), np.nan)
    if not len(f_obs):
        return out
    ln = np.log2(f_obs)
    lng = np.log2(grid)
    for i, c in enumerate(lng):
        w = w_obs * np.exp(-0.5 * ((ln - c) / sigma_oct) ** 2)
        keep = w > 1e-6 * w.max()
        if not keep.any():
            continue
        out[i] = m.weighted_quantile(y_obs[keep], w[keep], 0.5)
    return out


def load_timbre_observations(gain_db: float) -> pd.DataFrame:
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    fund = fund.copy()
    ton = ton.copy()
    fund["y_timbre"] = fund.y - gain_db
    ton["y_timbre"] = ton.y  # already relative
    fund["w"] = fund.weight_base * np.clip((fund.snr - 6) / 24, 0.08, 1.5)
    ton["w"] = ton.weight_base * 0.55 * np.clip((ton.snr - 6) / 24, 0.08, 1.5)
    cols = ["pair", "family", "string", "register", "phase", "f", "y_timbre", "w", "snr", "match_cost"]
    return pd.concat([fund[cols], ton[cols]], ignore_index=True)


def pair_first_curves(obs: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Median within each pair on PAIR_F, then median across pairs."""
    # Apply regional phase mix as observation weights.
    obs = obs.copy()
    obs["w_mix"] = obs.w * _phase_mix_weight(obs.f.to_numpy(), obs.phase.to_numpy())

    pair_curves = {}
    for pair, g in obs.groupby("pair"):
        pair_curves[pair] = _local_median(g.f, g.y_timbre, g.w_mix, PAIR_F)

    mat = np.vstack([pair_curves[p] for p in sorted(pair_curves)])
    # Per-frequency median across pairs (ignore NaN).
    with np.errstate(all="ignore"):
        across = np.nanmedian(mat, axis=0)
        mad = 1.4826 * np.nanmedian(np.abs(mat - across), axis=0)
        n_pairs = np.sum(np.isfinite(mat), axis=0)

    # Attack–sustain disagreement from phase-restricted pair curves.
    att_mat, sus_mat = [], []
    for pair, g in obs.groupby("pair"):
        ga = g[g.phase == "attack"]
        gs = g[g.phase == "sustain"]
        att_mat.append(_local_median(ga.f, ga.y_timbre, ga.w_mix, PAIR_F))
        sus_mat.append(_local_median(gs.f, gs.y_timbre, gs.w_mix, PAIR_F))
    att = np.nanmedian(np.vstack(att_mat), axis=0)
    sus = np.nanmedian(np.vstack(sus_mat), axis=0)
    disagreement = np.abs(att - sus)

    table = pd.DataFrame(
        {
            "frequency_hz": PAIR_F,
            "pair_first_db": across,
            "pair_mad_db": mad,
            "n_pairs": n_pairs,
            "attack_db": att,
            "sustain_db": sus,
            "attack_sustain_disagreement_db": disagreement,
        }
    )
    # Also stash per-pair matrix for LOO smoothing.
    return table, mat


def gaussian_smooth_log(curve: np.ndarray, freq: np.ndarray, width_oct: float) -> np.ndarray:
    """Variable-width gaussian smooth in log2-frequency (octaves)."""
    y = np.asarray(curve, float)
    f = np.asarray(freq, float)
    ln = np.log2(f)
    sigma = float(width_oct)
    out = np.empty_like(y)
    for i in range(len(f)):
        w = np.exp(-0.5 * ((ln - ln[i]) / sigma) ** 2)
        w[np.abs(ln - ln[i]) > 4 * sigma] = 0.0
        msk = np.isfinite(y) & (w > 0)
        if not msk.any():
            out[i] = np.nan
            continue
        ww = w[msk]
        out[i] = float(np.sum(ww * y[msk]) / np.sum(ww))
    return out


def select_regional_smoothing(
    pair_mat: np.ndarray, freq: np.ndarray
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Leave-one-pair-out width selection with 0.08 dB parsimony (V4.1 §33–34)."""
    n_pairs, n_f = pair_mat.shape
    selected = []
    width_profile = np.full(n_f, np.nan)

    for lo, hi, candidates, name in SMOOTH_CANDIDATES:
        band = (freq >= lo) & (freq < hi)
        if not band.any():
            continue
        scores = []
        for width in candidates:
            maes = []
            for k in range(n_pairs):
                train = np.nanmedian(np.delete(pair_mat, k, axis=0), axis=0)
                held = pair_mat[k]
                sm = gaussian_smooth_log(train, freq, width)
                msk = band & np.isfinite(sm) & np.isfinite(held)
                if not msk.any():
                    continue
                maes.append(float(np.median(np.abs(sm[msk] - held[msk]))))
            med = float(np.median(maes)) if maes else np.inf
            scores.append((width, med, float(np.mean(maes)) if maes else np.inf))

        scores.sort(key=lambda t: t[1])
        best_mae = scores[0][1]
        # Among widths within parsimony of best, pick the widest (smoothest).
        pool = [s for s in scores if s[1] <= best_mae + PARSIMONY_DB]
        chosen = max(pool, key=lambda t: t[0])
        selected.append(
            {
                "region": name,
                "low_hz": lo,
                "high_hz": hi,
                "width_octaves": chosen[0],
                "held_out_mae_db": chosen[1],
                "best_mae_db": best_mae,
                "candidates_tried": len(candidates),
                "parsimony_db": PARSIMONY_DB,
            }
        )
        width_profile[band] = chosen[0]

        # Record all candidates for transparency.
        for width, mae, mean_mae in scores:
            selected[-1].setdefault("_all", []).append(
                {"width_octaves": width, "mae_db": mae, "mean_mae_db": mean_mae}
            )

    # Expand candidate detail to a long CSV.
    detail_rows = []
    summary_rows = []
    for row in selected:
        summary_rows.append({k: v for k, v in row.items() if k != "_all"})
        for c in row.get("_all", []):
            detail_rows.append({"region": row["region"], **c, "selected": c["width_octaves"] == row["width_octaves"]})

    # Smooth the width profile itself (~1/12 oct) so regions don't seam.
    wp = width_profile.copy()
    # Fill edges.
    finite = np.isfinite(wp)
    if finite.any():
        wp[~finite] = np.interp(np.log(freq[~finite]), np.log(freq[finite]), wp[finite])
    wp_smooth = gaussian_smooth_log(wp, freq, 1 / 12)

    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows), wp_smooth


def apply_variable_smooth(curve: np.ndarray, freq: np.ndarray, width_oct: np.ndarray) -> np.ndarray:
    y = np.asarray(curve, float)
    f = np.asarray(freq, float)
    ln = np.log2(f)
    out = np.empty_like(y)
    for i in range(len(f)):
        sigma = max(float(width_oct[i]), 1e-3)
        w = np.exp(-0.5 * ((ln - ln[i]) / sigma) ** 2)
        w[np.abs(ln - ln[i]) > 4 * sigma] = 0.0
        msk = np.isfinite(y) & (w > 0)
        if not msk.any():
            out[i] = np.nan
            continue
        ww = w[msk]
        out[i] = float(np.sum(ww * y[msk]) / np.sum(ww))
    return out


def leave_one_pair_sensitivity(pair_mat: np.ndarray, freq: np.ndarray, width_oct: np.ndarray) -> np.ndarray:
    """Max |Δcurve| when dropping one pair, after regional smoothing."""
    n_pairs = pair_mat.shape[0]
    base = apply_variable_smooth(np.nanmedian(pair_mat, axis=0), freq, width_oct)
    max_change = np.zeros(len(freq))
    for k in range(n_pairs):
        train = np.nanmedian(np.delete(pair_mat, k, axis=0), axis=0)
        sm = apply_variable_smooth(train, freq, width_oct)
        d = np.abs(sm - base)
        d = np.nan_to_num(d, nan=0.0)
        max_change = np.maximum(max_change, d)
    return max_change


def geometric_reliability(
    freq: np.ndarray,
    n_pairs: np.ndarray,
    pair_mad: np.ndarray,
    disagreement: np.ndarray,
    loo_max: np.ndarray,
    ci_width: np.ndarray | None = None,
) -> pd.DataFrame:
    """V4.1 §40–41 geometric reliability, knees recalibrated to our support.

    MAD is used once (repeatability), not triple-counted as SNR/effective too —
    that was collapsing median reliability to ~0.05 and making shrink useless.
    """
    mad = np.nan_to_num(pair_mad, nan=6.0)
    support_score = np.clip(n_pairs / 8.0, 0.0, 1.0)
    # Effective: how many pairs are finite at this bin (already in n_pairs) × MAD.
    effective_score = np.clip((n_pairs - 1.0) / 6.0, 0.0, 1.0) * np.clip(np.exp(-mad / 6.0), 0.05, 1.0)
    snr_proxy = np.clip(np.exp(-mad / 8.0), 0.05, 1.0)
    repeatability = np.clip(np.exp(-mad / 6.0), 0.05, 1.0)
    phase_score = np.clip(np.exp(-np.nan_to_num(disagreement, nan=6.0) / 6.0), 0.05, 1.0)
    loo_score = np.clip(np.exp(-np.nan_to_num(loo_max, nan=6.0) / 6.0), 0.05, 1.0)
    if ci_width is None:
        bootstrap_score = np.ones_like(freq, float)
    else:
        bootstrap_score = np.clip(np.exp(-np.asarray(ci_width, float) / 8.0), 0.05, 1.0)

    eps = 1e-6
    base = (
        np.maximum(support_score, eps) ** 0.20
        * np.maximum(effective_score, eps) ** 0.12
        * np.maximum(snr_proxy, eps) ** 0.17
        * np.maximum(repeatability, eps) ** 0.14
        * np.maximum(bootstrap_score, eps) ** 0.16
        * np.maximum(loo_score, eps) ** 0.11
        * np.maximum(phase_score, eps) ** 0.10
    )
    rel = base * v12.codec_prior(freq)
    rel = rel * v12.mains_factor(freq, 30.0 - 8.0 * mad)

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
            "snr_proxy_score": snr_proxy,
            "repeatability": repeatability,
            "bootstrap_score": bootstrap_score,
            "loo_score": loo_score,
            "phase_score": phase_score,
            "codec_prior": v12.codec_prior(freq),
            "reliability": out,
        }
    )


def non_open_sustain_gain(fund: pd.DataFrame, curve_db: np.ndarray) -> dict:
    """V4.1 §44: sustain, non-open, decent match cost."""
    qfun = m.curve_fun(curve_db)
    z = fund[
        (fund.snr >= 10)
        & (fund.match_cost <= 2.8)
        & (fund.phase == "sustain")
        & (fund.family != "open")
    ].copy()
    z["g_need"] = z.y - z.f.apply(qfun)
    z = z[z.g_need >= v11.COLLAPSE_THRESHOLD_DB]
    if not len(z):
        return {"n": 0, "median_db": float("nan")}
    from scipy import stats as _stats

    per_pair = z.groupby("pair").g_need.median()
    vals = per_pair.to_numpy(float)
    rng = np.random.default_rng(991)
    boots = [
        float(np.median(rng.choice(vals, size=len(vals), replace=True)))
        for _ in range(2000)
    ]
    return {
        "n_observations": int(len(z)),
        "n_pairs": int(len(per_pair)),
        "median_db": float(np.median(vals)),
        "trimmed_mean_10_db": float(_stats.trim_mean(vals, 0.1)),
        "bootstrap_p025_db": float(np.percentile(boots, 2.5)),
        "bootstrap_p975_db": float(np.percentile(boots, 97.5)),
        "pairs": {k: float(v) for k, v in per_pair.round(3).items()},
    }


def upsample_to_dense(freq_src, values, freq_dst):
    ok = np.isfinite(values) & (freq_src > 0)
    return np.interp(np.log(freq_dst), np.log(freq_src[ok]), values[ok])


def main() -> None:
    t0 = time.time()
    run_id = f"v14_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(run_id, pipeline="emulate_azul_v14", stages=["improve_v14"])

    # Reference gain: V12 energy-neutral.
    if (OUT / "RESUMEN_V12.json").exists():
        gain = float(json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"])
    else:
        gain = float(json.loads((OUT / "RESUMEN_V13.json").read_text())["reference_gain_db"])
    print(f"1 gain reference {gain:+.3f} dB", flush=True)

    obs = load_timbre_observations(gain)
    print(f"2 timbre observations {len(obs)}", flush=True)

    print("3 pair-first aggregation + attack/sustain disagreement", flush=True)
    pair_table, pair_mat = pair_first_curves(obs)
    pair_table.to_csv(OUT / "CURVA_PAIR_FIRST_V14.csv", index=False)

    print("4 regional held-out smoothing", flush=True)
    smooth_summary, smooth_detail, width_profile = select_regional_smoothing(pair_mat, PAIR_F)
    smooth_summary.to_csv(OUT / "SUAVIZADO_REGIONAL_V14.csv", index=False)
    smooth_detail.to_csv(OUT / "SUAVIZADO_REGIONAL_CANDIDATOS_V14.csv", index=False)
    print(smooth_summary.round(4).to_string(index=False), flush=True)

    raw = pair_table.pair_first_db.to_numpy(float)
    smoothed = apply_variable_smooth(raw, PAIR_F, width_profile)

    print("5 leave-one-pair sensitivity", flush=True)
    loo_max = leave_one_pair_sensitivity(pair_mat, PAIR_F, width_profile)

    # Energy neutrality on pair-first smoothed curve.
    ref = v12.cafe_reference_spectrum(PAIR_F)
    neutral, effect = v12.energy_neutralize(np.nan_to_num(smoothed, nan=0.0), ref)
    gain_pair_first = gain + effect
    print(f"   energy effect {effect:+.3f} dB → gain_pair_first {gain_pair_first:+.3f} dB", flush=True)

    print("6 geometric reliability (recalibrated)", flush=True)
    # CI width proxy from pair MAD.
    ci_proxy = 2.0 * 1.96 * pair_table.pair_mad_db.to_numpy(float) / np.sqrt(np.maximum(pair_table.n_pairs, 1))
    rel = geometric_reliability(
        PAIR_F,
        pair_table.n_pairs.to_numpy(float),
        pair_table.pair_mad_db.to_numpy(float),
        pair_table.attack_sustain_disagreement_db.to_numpy(float),
        loo_max,
        ci_proxy,
    )
    recommended, const = v12.shrink_to_reliability(neutral, rel.reliability.to_numpy(), ref)
    print(
        f"   reliability median {rel.reliability.median():.3f} "
        f"p10 {rel.reliability.quantile(0.1):.3f} p90 {rel.reliability.quantile(0.9):.3f}",
        flush=True,
    )
    print(f"   shrink constant {const:+.3f} dB", flush=True)

    curve = pd.DataFrame(
        {
            "frequency_hz": PAIR_F,
            "pair_first_raw_db": raw,
            "pair_first_smoothed_db": smoothed,
            "energy_neutral_db": neutral,
            "recommended_db": recommended,
            "smoothing_width_octaves": width_profile,
            "pair_mad_db": pair_table.pair_mad_db,
            "n_pairs": pair_table.n_pairs,
            "attack_sustain_disagreement_db": pair_table.attack_sustain_disagreement_db,
            "loo_max_change_db": loo_max,
            "reliability": rel.reliability,
            "pipeline_version": "V14.0",
        }
    )
    curve.to_csv(OUT / "CURVAS_DENSAS_V14.csv", index=False)
    rel.to_csv(OUT / "FIABILIDAD_V14.csv", index=False)

    # Upsample recommended/neutral onto the V12 4096 grid for fair comparison.
    v12c = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
    v12_n = np.interp(np.log(m.DENSE_F), np.log(v12c.frequency_hz), v12c.energy_neutral_db)
    v14_n = upsample_to_dense(PAIR_F, neutral, m.DENSE_F)
    v14_r = upsample_to_dense(PAIR_F, recommended, m.DENSE_F)

    v41 = {515: 3.49, 958: 3.49, 1360: 4.08, 2630: 6.61, 4120: 6.34, 5190: 4.33}
    rows = []
    for hz, theirs in v41.items():
        rows.append(
            {
                "frequency_hz": hz,
                "v12_neutral_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), v12_n)),
                "v14_neutral_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), v14_n)),
                "v14_recommended_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), v14_r)),
                "v41_reported_db": theirs,
            }
        )
    cross = pd.DataFrame(rows)
    cross["v14_neutral_minus_v41"] = cross.v14_neutral_db - cross.v41_reported_db
    cross["v12_neutral_minus_v41"] = cross.v12_neutral_db - cross.v41_reported_db
    cross.to_csv(OUT / "COMPARACION_V14_VS_V41.csv", index=False)
    print(cross.round(2).to_string(index=False), flush=True)

    # Regional RMSE V14 vs V12 (shape after removing mean offset in 250-6000).
    regions = [(20, 60), (60, 250), (250, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 18000)]
    reg_rows = []
    for a, b in regions:
        sel = (m.DENSE_F >= a) & (m.DENSE_F < b)
        d = v14_n[sel] - v12_n[sel]
        # Offset-removed shape error in presence band sense.
        d0 = d - np.mean(d)
        reg_rows.append(
            {
                "region": f"{a}-{b}",
                "mean_delta_db": float(np.mean(d)),
                "rmse_db": float(np.sqrt(np.mean(d**2))),
                "rmse_shape_db": float(np.sqrt(np.mean(d0**2))),
            }
        )
    pd.DataFrame(reg_rows).to_csv(OUT / "COMPARACION_V14_VS_V12.csv", index=False)

    print("7 non-open sustain gain (V4.1 §44)", flush=True)
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    # Use V12 curve on dense grid for residual gain.
    g_nonopen = non_open_sustain_gain(fund, v12_n)
    (OUT / "GAIN_NO_OPEN_SUSTAIN_V14.json").write_text(
        json.dumps(g_nonopen, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in g_nonopen.items() if k != "pairs"}, indent=2), flush=True)

    # Optional: one closed-loop fit with regional phase mix weights (diagnostic).
    print("8 diagnostic refit with regional phase mix", flush=True)
    windows = pd.read_csv(OUT / "VENTANAS_ADAPTATIVAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()
    res["weight_base"] *= 0.35
    obs_raw = fund.to_dict("records") + ton.to_dict("records") + res.to_dict("records")
    rw = v12.reweight_observations(obs_raw, windows)
    mix = _phase_mix_weight(rw.f.to_numpy(), rw.phase.to_numpy())
    # Replace fixed PHASE_W influence: scale by mix / mean phase weight.
    rw["weight_base_v14"] = rw.weight_base_v12 * mix
    obs_fit = (
        rw.drop(columns=["weight_base"])
        .rename(columns={"weight_base_v14": "weight_base"})
    )
    obs_fit = obs_fit[obs_fit.weight_base > 0].to_dict("records")
    lc, _lr, _ = run_config.lambdas()
    if lc is None:
        lc = (100, 20, 80, 1)
    beta, dfn, gain_loop, history, _pp = v11.close_gain_curve_loop(obs_fit, lc, fund, gain)
    curve_fit = m.eval_q(beta)
    fit_neutral, fit_effect = v12.energy_neutralize(curve_fit, v12.cafe_reference_spectrum(m.DENSE_F))
    history.to_csv(OUT / "CONVERGENCIA_GAIN_CURVA_V14.csv", index=False)

    # Publish dense fit curve.
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "diagnostic_db": curve_fit,
            "energy_neutral_db": fit_neutral,
            "pipeline_version": "V14.0-phase-mix-fit",
        }
    ).to_csv(OUT / "CURVAS_DENSAS_V14_FIT.csv", index=False)

    summary = {
        "run_id": run_id,
        "gain_v12_energy_neutral_db": gain,
        "gain_pair_first_neutral_db": gain_pair_first,
        "gain_phase_mix_loop_db": float(gain_loop),
        "gain_phase_mix_neutral_db": float(gain_loop + fit_effect),
        "gain_non_open_sustain_median_db": g_nonopen.get("median_db"),
        "gain_non_open_sustain_ci95_db": [
            g_nonopen.get("bootstrap_p025_db"),
            g_nonopen.get("bootstrap_p975_db"),
        ],
        "reliability_median": float(rel.reliability.median()),
        "reliability_p10": float(rel.reliability.quantile(0.1)),
        "phase_disagreement_median_db": float(
            pair_table.attack_sustain_disagreement_db.median()
        ),
        "smoothing_widths": smooth_summary[["region", "width_octaves", "held_out_mae_db"]].to_dict(
            "records"
        ),
        "v41_cross_rmse_v12_db": float(np.sqrt(np.mean(cross.v12_neutral_minus_v41**2))),
        "v41_cross_rmse_v14_db": float(np.sqrt(np.mean(cross.v14_neutral_minus_v41**2))),
        "v14_vs_v12_presence_2k4k_rmse_db": float(
            pd.DataFrame(reg_rows).set_index("region").loc["2000-4000", "rmse_db"]
        ),
        "loop_iterations": int(len(history)),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V14.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
