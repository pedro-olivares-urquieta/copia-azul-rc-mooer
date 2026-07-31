"""V17: hybrid faithful copy — beat hold-out without smoothing.

Combines what worked:

* V15 enrich weights + single presence scale (best copy so far)
* V16 per-pair RMS demean (§24)
* V4.1 §31 pair weights from alignment confidence (not flat median)
* V4.1 §29.1 repetibility: down-weight phases that disagree
* Fretted-only shape option (open strings only for sub-300 Hz)

No octave smoothing. No reliability shrink. Hold-out decides the operative curve.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import AUD, OUT, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v14 as v14  # noqa: E402
import improve_v15 as v15  # noqa: E402
import improve_v16 as v16  # noqa: E402
import run_manifest  # noqa: E402

# Match V15 localization (1/10 oct); 1/12 was slightly worse for fidelity.
LOCAL_OCT = 1.0 / 10.0
CALIB_PAIRS = v16.CALIB_PAIRS
HOLD_PAIRS = v16.HOLD_PAIRS
ALL_TEST = [
    "A_12",
    "B_12",
    "C_12",
    "D_12",
    "E_12",
    "G_12",
    "C_24",
    "C_chromatic",
]


def pair_alignment_weights() -> pd.DataFrame:
    match = pd.read_csv(OUT / "MATCHING_EVENTOS_V10_2.csv")
    rows = []
    for pair, g in match.groupby("pair"):
        cost = float(g.match_cost.median())
        # V4.1-like: quantity ratio is ~1 after our DP match; penalise cost + low conf.
        low_frac = float((g.confidence == "low").mean())
        high_frac = float((g.confidence == "high").mean())
        # Map cost~1.4→1.0, cost~2.2→0.45
        cost_w = float(np.clip(1.35 - 0.40 * cost, 0.35, 1.0))
        conf_w = float(np.clip(1.0 - 0.65 * low_frac + 0.20 * high_frac, 0.25, 1.0))
        # §26-ish event confidence.
        w = cost_w * conf_w
        rows.append(
            {
                "pair": pair,
                "match_cost_median": cost,
                "low_frac": low_frac,
                "pair_weight": w,
                "n_events": int(len(g)),
            }
        )
    return pd.DataFrame(rows)


def weighted_nanmedian(mat: np.ndarray, weights: np.ndarray) -> np.ndarray:
    out = np.empty(mat.shape[1])
    for i in range(mat.shape[1]):
        col = mat[:, i]
        ok = np.isfinite(col) & np.isfinite(weights) & (weights > 0)
        if not ok.any():
            out[i] = np.nan
            continue
        out[i] = m.weighted_quantile(col[ok], weights[ok], 0.5)
    return out


def phase_repeatability_weights(obs: pd.DataFrame) -> pd.DataFrame:
    """§29.1: within each pair×freq-neighborhood, shrink flaky phases.

    Approximated per pair×phase via MAD of y_timbre (global per pair-phase),
    then multiplied into observation weights.
    """
    z = obs.copy()
    stats = (
        z.groupby(["pair", "phase"])
        .y_timbre.agg(med="median", mad=lambda s: float(1.4826 * np.median(np.abs(s - np.median(s)))))
        .reset_index()
    )
    stats["rep"] = np.exp(-stats.mad.clip(lower=0) / 4.5)
    z = z.merge(stats[["pair", "phase", "rep"]], on=["pair", "phase"], how="left")
    z["rep"] = z.rep.fillna(0.5)
    z["w"] = z.w * z.rep
    return z


def build_pair_matrix(
    obs: pd.DataFrame,
    pairs: list[str],
    fretted_only_above_hz: float | None = 300.0,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Pair curves on PAIR_F. Optionally drop open-string obs above 300 Hz."""
    z = obs[obs.w > 0].copy()
    if fretted_only_above_hz is not None:
        drop = (z.family == "open") & (z.f > fretted_only_above_hz)
        z = z[~drop]
    order = [p for p in pairs if p in set(z.pair)]
    mats = []
    for pair in order:
        g = z[z.pair == pair]
        mats.append(v14._local_median(g.f, g.y_timbre, g.w, v14.PAIR_F, LOCAL_OCT))
    return np.vstack(mats), v14.PAIR_F, order


def aggregate_variants(obs: pd.DataFrame, pair_w: pd.DataFrame) -> dict[str, np.ndarray]:
    """Several unsmoothed aggregators to race on hold-out."""
    all_pairs = sorted(obs.pair.unique())
    wmap = pair_w.set_index("pair")["pair_weight"].to_dict()

    variants = {}
    # A: all pairs, flat median (V16-like after demean)
    mat, freq, order = build_pair_matrix(obs, all_pairs, fretted_only_above_hz=None)
    variants["flat_all"] = np.nanmedian(mat, axis=0)

    # B: confidence-weighted median, all pairs
    ww = np.array([wmap.get(p, 0.5) for p in order], float)
    variants["weighted_all"] = weighted_nanmedian(mat, ww)

    # C: fretted-primary (open only ≤300), weighted
    mat_f, _, order_f = build_pair_matrix(obs, all_pairs, fretted_only_above_hz=300.0)
    ww_f = np.array([wmap.get(p, 0.5) for p in order_f], float)
    variants["weighted_fretted"] = weighted_nanmedian(mat_f, ww_f)

    # D: exclude chords from shape (V4.1 physical spirit without fixed 0.85)
    no_chord = [p for p in all_pairs if p not in ("Am7", "Cmaj7")]
    mat_nc, _, order_nc = build_pair_matrix(obs, no_chord, fretted_only_above_hz=300.0)
    ww_nc = np.array([wmap.get(p, 0.5) for p in order_nc], float)
    variants["weighted_fretted_nochord"] = weighted_nanmedian(mat_nc, ww_nc)

    return variants


def to_dense_neutral(curve_pair: np.ndarray) -> tuple[np.ndarray, float]:
    ref = v12.cafe_reference_spectrum(v14.PAIR_F)
    neu, eff = v12.energy_neutralize(np.nan_to_num(curve_pair, nan=0.0), ref)
    dense = v15.upsample_faithful(v14.PAIR_F, neu, m.DENSE_F)
    return dense, eff


def main() -> None:
    t0 = time.time()
    run_id = f"v17_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v17", stages=["improve_v17"]
    )

    g12 = float(json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"])
    pair_gains = v16.pair_scalar_gains()
    global_scalar = float(pair_gains.gain_scalar_db.median())
    print(f"1 scalar median {global_scalar:+.3f} dB", flush=True)

    print("2 observations (demeaned + V15-style) + phase repetibility", flush=True)
    obs_demean = phase_repeatability_weights(
        v16.demeaned_observations(g12, pair_gains)
    )
    # Same enrich path as V15 (global gain only) — historically better for copy.
    obs_v15 = phase_repeatability_weights(v15.enrich_observations(g12))
    pair_w = pair_alignment_weights()
    pair_w.to_csv(OUT / "PESOS_PAREJA_ALINEACION_V17.csv", index=False)
    print(pair_w.sort_values("pair_weight").round(3).to_string(index=False), flush=True)

    print("3 unsmoothed aggregators", flush=True)
    variants_pair = {}
    for prefix, obs in (("dm", obs_demean), ("v15w", obs_v15)):
        for name, curve_p in aggregate_variants(obs, pair_w).items():
            variants_pair[f"{prefix}_{name}"] = curve_p

    # Calibrate each on CALIB; score on HOLD.
    results = []
    dense_store = {}
    for name, curve_p in variants_pair.items():
        dense, eff = to_dense_neutral(curve_p)
        # V15-style obs already demeaned by global g12 inside enrich; residual
        # energy effect rides on g12. Demeaned path uses per-pair scalar median.
        gain0 = (global_scalar if name.startswith("dm_") else g12) + eff
        dense_cal, scale, gain_cal = v15.calibrate_presence_scale(
            dense, gain0, CALIB_PAIRS
        )
        dense_store[name] = (dense, dense_cal, gain_cal, scale)
        hold = v15.fidelity_audit(dense_cal, gain_cal, name, pairs=HOLD_PAIRS)
        crit = hold[hold.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
        score = float(crit.rmse_db.median())
        bias24 = float(
            hold.loc[hold.band == "2k-4k", "bias_db"].median()
        )
        results.append(
            {
                "variant": f"v17_{name}",
                "holdout_critical_rmse_db": score,
                "bias_2k4k_db": bias24,
                "presence_scale": scale,
                "gain_db": gain_cal,
            }
        )
        print(
            f"   {name}: hold RMSE {score:.3f}  scale {scale:.3f}  gain {gain_cal:+.3f}",
            flush=True,
        )

    # Baselines — fair hold-out: re-calibrate V15 detail on CALIB_PAIRS only.
    # (Published V15 calibrated on G_12/C_24 too, which overlap HOLD_PAIRS.)
    v12c = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
    c12 = np.interp(np.log(m.DENSE_F), np.log(v12c.frequency_hz), v12c.energy_neutral_db)
    v15c = pd.read_csv(OUT / "CURVAS_DENSAS_V15_FIEL.csv")
    c15_pub = np.interp(np.log(m.DENSE_F), np.log(v15c.frequency_hz), v15c.eq_faithful_db)
    g15_pub = float(json.loads((OUT / "RESUMEN_V15.json").read_text())["gain_faithful_db"])
    detail15 = np.interp(
        np.log(m.DENSE_F), np.log(v15c.frequency_hz), v15c.eq_observed_detail_db
    )
    g15_detail = float(
        json.loads((OUT / "RESUMEN_V15.json").read_text()).get(
            "gain_observed_detail_db", g15_pub
        )
    )
    c15, s15, g15 = v15.calibrate_presence_scale(detail15, g15_detail, CALIB_PAIRS)
    dense_store["v15_recal"] = (detail15, c15, g15, s15)
    v16c = pd.read_csv(OUT / "CURVAS_DENSAS_V16_FIEL.csv")
    c16 = np.interp(np.log(m.DENSE_F), np.log(v16c.frequency_hz), v16c.eq_faithful_db)
    g16 = float(json.loads((OUT / "RESUMEN_V16.json").read_text())["gain_faithful_db"])

    for label, curve_d, g, scale in (
        ("v12_energy_neutral", c12, g12, np.nan),
        ("v15_faithful_recal", c15, g15, s15),
        ("v15_faithful_published", c15_pub, g15_pub, np.nan),
        ("v16_faithful", c16, g16, np.nan),
    ):
        hold = v15.fidelity_audit(curve_d, g, label, pairs=HOLD_PAIRS)
        crit = hold[hold.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
        results.append(
            {
                "variant": label,
                "holdout_critical_rmse_db": float(crit.rmse_db.median()),
                "bias_2k4k_db": float(hold.loc[hold.band == "2k-4k", "bias_db"].median()),
                "presence_scale": scale,
                "gain_db": g,
            }
        )

    ranking = pd.DataFrame(results)
    # Primary: hold-out RMSE. Near-ties (≤0.05 dB): prefer flatter 2–4 kHz bias.
    ranking["abs_bias_2k4k"] = ranking.bias_2k4k_db.abs()
    ranking = ranking.sort_values(
        ["holdout_critical_rmse_db", "abs_bias_2k4k"]
    ).reset_index(drop=True)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_HOLDOUT_V17.csv", index=False)
    print(ranking.round(3).to_string(index=False), flush=True)

    # Operative winner ignores published V15 (calibrated on HOLD pairs).
    fair = ranking[~ranking.variant.astype(str).str.contains("published")].copy()
    # Within 0.05 dB of the best fair RMSE, pick lowest |2–4 kHz bias|.
    best_rmse = float(fair.holdout_critical_rmse_db.min())
    near = fair[fair.holdout_critical_rmse_db <= best_rmse + 0.05]
    best = near.sort_values(["abs_bias_2k4k", "holdout_critical_rmse_db"]).iloc[0]
    best_name = str(best.variant)
    print(
        f"4 winner (fair hold-out, presence-aware): {best_name} "
        f"RMSE={best.holdout_critical_rmse_db:.3f} "
        f"bias2k4k={best.bias_2k4k_db:+.3f}",
        flush=True,
    )

    # Resolve operative curve (fair hold-out winner; published V15 only if it wins).
    if best_name.startswith("v17_"):
        key = best_name.replace("v17_", "")
        op_curve, op_gain = dense_store[key][1], dense_store[key][2]
        op_scale = dense_store[key][3]
        detail = dense_store[key][0]
    elif best_name in ("v15_faithful_recal", "v15_recal"):
        op_curve, op_gain, op_scale, detail = c15, g15, s15, detail15
    elif best_name == "v15_faithful_published":
        op_curve, op_gain, op_scale, detail = c15_pub, g15_pub, np.nan, c15_pub
    elif best_name == "v16_faithful":
        op_curve, op_gain, op_scale, detail = c16, g16, np.nan, c16
    else:
        op_curve, op_gain, op_scale, detail = c12, g12, np.nan, c12

    # Publish all v17 calibrated curves for inspection.
    rows = {"frequency_hz": m.DENSE_F}
    for name, (d0, dcal, gcal, sc) in dense_store.items():
        rows[f"detail_{name}_db"] = d0
        rows[f"faithful_{name}_db"] = dcal
    rows["eq_faithful_best_db"] = op_curve
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_DENSAS_V17.csv", index=False)

    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "source_variant": best_name,
            "smoothing": "none",
            "pipeline_version": "V17.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)

    pd.DataFrame(
        [
            {
                "gain_recommended_db": op_gain,
                "gain_source": best_name,
                "presence_scale": op_scale,
                "smoothing": "none",
                "pipeline_version": "V17.0-operative",
            }
        ]
    ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)

    # Also mirror into published-style names for bridge consumers (non-destructive).
    # Keep V10.2 intact; write companion files.
    impl = {
        "version": "V17.0",
        "smoothing": "none",
        "operative_curve_csv": "CURVA_COPIA_OPERATIVA.csv",
        "operative_gain_csv": "GAIN_COPIA_OPERATIVA.csv",
        "operative_variant": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if np.isnan(op_scale) else float(op_scale),
        "holdout_ranking": ranking.to_dict("records"),
        "calib_pairs": CALIB_PAIRS,
        "hold_pairs": HOLD_PAIRS,
        "intent": "Faithful Azul copy from existing sessions; no octave smoothing.",
    }
    (OUT / "IMPLEMENTACION_FIEL_V17.json").write_text(
        json.dumps(impl, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Full fretted audit for the winner + baselines.
    print("5 full fretted audit", flush=True)
    audits = []
    for label, curve_d, g in (
        ("operative", op_curve, op_gain),
        ("v15_faithful_recal", c15, g15),
        ("v15_faithful_published", c15_pub, g15_pub),
        ("v16_faithful", c16, g16),
        ("v12_energy_neutral", c12, g12),
    ):
        audits.append(v15.fidelity_audit(curve_d, g, label, pairs=ALL_TEST))
    audit = pd.concat(audits, ignore_index=True)
    audit.to_csv(OUT / "FIDELIDAD_RENDER_V17.csv", index=False)
    summ = v15.summarize_fidelity(audit)
    summ.to_csv(OUT / "FIDELIDAD_RENDER_RESUMEN_V17.csv", index=False)
    print(
        summ[summ.band == "2k-4k"][["variant", "rmse_median_db", "bias_median_db"]]
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
                "operative_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), op_curve)),
                "v15_recal_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c15)),
                "v15_published_db": float(
                    np.interp(np.log(hz), np.log(m.DENSE_F), c15_pub)
                ),
                "v16_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c16)),
                "v12_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c12)),
                "v41_db": theirs,
            }
        )
    pd.DataFrame(pts).to_csv(OUT / "COMPARACION_V17_VS_V41.csv", index=False)
    print(pd.DataFrame(pts).round(2).to_string(index=False), flush=True)

    print("6 proof audio + FIR note", flush=True)
    import soundfile as sf

    proof = AUD / "FIDELIDAD_V17"
    proof.mkdir(parents=True, exist_ok=True)
    key = "B_12"
    p = m.PAIRS[key]
    yc, _ = m.load(p["cafe"])
    ya, _ = m.load(p["azul"])
    z = m.apply_eq(yc, m.fir_from_curve(op_curve), op_gain)
    L = min(len(z), len(ya))
    sf.write(proof / "AZUL_ORIGINAL.flac", ya[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_COPIA_OPERATIVA.flac", z[:L], m.SR, subtype="PCM_24")
    sf.write(
        proof / "ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac",
        np.column_stack([z[:L], ya[:L]]),
        m.SR,
        subtype="PCM_24",
    )

    summary = {
        "run_id": run_id,
        "intent": "faithful_copy_without_smoothing",
        "winner": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if np.isnan(op_scale) else float(op_scale),
        "holdout_rmse_db": float(best.holdout_critical_rmse_db),
        "ranking": ranking.to_dict("records"),
        "operative_files": [
            "CURVA_COPIA_OPERATIVA.csv",
            "GAIN_COPIA_OPERATIVA.csv",
            "IMPLEMENTACION_FIEL_V17.json",
        ],
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V17.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Keep IMPLEMENTACION_FIEL_V16.json pointer fresh for older docs.
    (OUT / "IMPLEMENTACION_FIEL_V16.json").write_text(
        json.dumps({**impl, "superseded_by": "IMPLEMENTACION_FIEL_V17.json"}, indent=2),
        encoding="utf-8",
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
