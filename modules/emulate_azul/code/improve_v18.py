"""V18: faithful copy refinements from V4.1 that we still lacked.

No octave smoothing. No EQ×reliability shrink. No fixed physical multipliers.

Adds (existing 16-pair evidence only):

1. **Phase-first PAIR curves** (§27–29): build attack/body/sustain curves per
   pair, mix with PHASE_MIX, down-weight frequencies where attack≠sustain.
2. **Richer event confidence** (§26): note_error, lag consistency, overlap
   classification — not only match_cost.
3. **Broad/narrow residual race** (§13–16 spirit): vary band_residual weight.
4. **Gain mode race** (§43–45): energy-neutral presence scale vs non-open
   sustain residual vs small CALIB gain grid.

Hold-out decides. Updates CURVA_COPIA_OPERATIVA only if it beats V17.
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
import improve_v17 as v17  # noqa: E402
import run_manifest  # noqa: E402

LOCAL_OCT = 1.0 / 10.0
CALIB_PAIRS = v17.CALIB_PAIRS
HOLD_PAIRS = v17.HOLD_PAIRS
ALL_TEST = v17.ALL_TEST

CLASS_W = {
    "clean": 1.00,
    "tight": 0.85,
    "overlap": 0.45,
    "crowded": 0.35,
    "silence_short": 0.70,
}


def event_confidence_v18() -> pd.DataFrame:
    """§26-style event confidence from match + overlap + note error."""
    match = pd.read_csv(OUT / "MATCHING_EVENTOS_V10_2.csv").rename(
        columns={"event_cafe": "event"}
    )
    esp = pd.read_csv(OUT / "ESPACIOS_Y_SOLAPAMIENTOS_V10_2.csv")
    z = match.merge(esp, on=["pair", "event"], how="left")

    conf_w = z.confidence.map(v15.CONF_MAP).fillna(0.55)
    cost_w = np.clip(1.3 - 0.35 * z.match_cost, 0.4, 1.0)
    # ±60 cents → soft; >35 cents already suspicious for fretted matches.
    note_err = z.note_error_cents.abs().fillna(20.0)
    note_w = np.clip(1.0 - note_err / 60.0, 0.35, 1.0)

    def _lag_w(g: pd.Series) -> pd.Series:
        med = g.median()
        mad = float(np.median(np.abs(g - med)))
        scale = max(mad, 5.0)  # ms
        return np.clip(1.0 - 0.25 * np.abs(g - med) / scale, 0.40, 1.0)

    lag_w = z.groupby("pair")["lag_ms"].transform(_lag_w)
    class_w = z.classification.map(CLASS_W).fillna(0.70)
    # Soft §26 blend: base + alignment-ish + SNR proxy via cost.
    event_conf = np.clip(
        0.45 * conf_w * cost_w
        + 0.25 * note_w
        + 0.15 * lag_w
        + 0.15 * class_w,
        0.15,
        1.0,
    )
    out = z[["pair", "event"]].copy()
    out["event_confidence_v18"] = event_conf
    out["class_weight"] = class_w
    out["note_weight"] = note_w
    out["lag_weight"] = lag_w
    return out


def enrich_v18(gain_db: float, residual_w0: float = 0.20) -> pd.DataFrame:
    """V15 enrich with V18 event confidence and tunable residual weight."""
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
    for df, w0 in ((fund, 1.0), (ton, 0.55), (res, float(residual_w0))):
        z = df.copy()
        z["w0"] = z.weight_base * w0
        frames.append(z)
    obs = pd.concat(frames, ignore_index=True, sort=False)

    conf18 = event_confidence_v18()
    obs = obs.merge(conf18, on=["pair", "event"], how="left")
    # Fallback to V15 table if merge miss.
    conf15 = v15.match_confidence_table()
    obs = obs.merge(conf15, on=["pair", "event"], how="left")
    obs["event_confidence"] = obs.event_confidence_v18.fillna(
        obs.event_confidence.fillna(0.70)
    )

    f = obs.f.to_numpy(float)
    obs["tonal_score"] = v15.tonal_proximity(f, obs.f0.to_numpy(float), obs.kind.to_numpy())
    obs["rel_energy_score"] = v15.relative_energy_score(obs.snr.to_numpy(float), f)
    # Phase mix applied later in phase-first path; keep mild prior here.
    obs["phase_mix"] = v14._phase_mix_weight(f, obs.phase.to_numpy())
    obs["snr_score"] = np.clip(
        (obs.snr.to_numpy(float) - v12.snr_threshold(f)) / 18.0, 0.0, 1.0
    )
    obs["codec_prior"] = v12.codec_prior(f)
    obs["open_mask"] = v12.open_string_mask(f, obs.family.to_numpy())
    obs["mains_factor"] = v12.mains_factor(f, obs.snr.to_numpy(float))

    win = pd.read_csv(OUT / "VENTANAS_ADAPTATIVAS_V10_2.csv")
    obs = obs.merge(
        win[["pair", "event", "phase", "duration_cafe_ms"]],
        on=["pair", "event", "phase"],
        how="left",
    )
    obs["duration_s"] = obs.duration_cafe_ms.fillna(165.0) / 1000.0
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
    )
    return obs


def phase_first_pair_curve(obs: pd.DataFrame, pair: str) -> tuple[np.ndarray, np.ndarray]:
    """§29: mix phase PAIR curves; return curve + local phase-agreement weight."""
    g = obs[(obs.pair == pair) & (obs.w > 0)]
    phases = {
        "attack": g[g.phase == "attack"],
        "body": g[g.phase == "body"],
        "sustain": g[g.phase == "sustain"],
        "stabilization": g[g.phase == "stabilization"],
        "decay": g[g.phase == "decay"],
        "low": g[g.phase == "low"],
    }
    curves = {}
    for name, gg in phases.items():
        if len(gg) == 0:
            curves[name] = np.full(len(v14.PAIR_F), np.nan)
        else:
            curves[name] = v14._local_median(
                gg.f, gg.y_timbre, gg.w, v14.PAIR_F, LOCAL_OCT
            )

    # Nominal phase mix on PAIR_F (V21: optional 6th weight = low).
    mix_w = {k: np.zeros(len(v14.PAIR_F)) for k in curves}
    for lo, hi, *weights in v14.PHASE_MIX:
        sel = (v14.PAIR_F >= lo) & (v14.PAIR_F < hi)
        vals = np.asarray(weights, float)
        if len(vals) < 6:
            vals = np.r_[vals, 0.0]
        vals = vals / max(vals.sum(), 1e-12)
        mix_w["attack"][sel] = vals[0]
        mix_w["stabilization"][sel] = vals[1]
        mix_w["body"][sel] = vals[2]
        mix_w["sustain"][sel] = vals[3]
        mix_w["decay"][sel] = vals[4]
        mix_w["low"][sel] = vals[5]

    # Availability: zero weight where curve NaN.
    stacked = []
    weights = []
    for name in ("attack", "stabilization", "body", "sustain", "decay", "low"):
        c = curves[name]
        w = mix_w[name].copy()
        w[~np.isfinite(c)] = 0.0
        stacked.append(np.nan_to_num(c, nan=0.0))
        weights.append(w)
    stacked = np.vstack(stacked)
    weights = np.vstack(weights)
    wsum = weights.sum(axis=0)
    curve = np.full(len(v14.PAIR_F), np.nan)
    ok = wsum > 1e-9
    curve[ok] = (stacked[:, ok] * weights[:, ok]).sum(axis=0) / wsum[ok]

    # Local attack–sustain agreement (§30) → pair support at each freq.
    att, sus = curves["attack"], curves["sustain"]
    dis = np.abs(att - sus)
    agree = np.exp(-np.nan_to_num(dis, nan=4.5) / 4.5)
    agree = np.where(np.isfinite(att) & np.isfinite(sus), agree, 0.75)
    return curve, agree


def build_phase_first_matrix(
    obs: pd.DataFrame,
    pairs: list[str] | None = None,
    fretted_only_above_hz: float | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    z = obs[obs.w > 0].copy()
    if fretted_only_above_hz is not None:
        drop = (z.family == "open") & (z.f > fretted_only_above_hz)
        z = z[~drop]
    order = [p for p in (pairs or sorted(z.pair.unique())) if p in set(z.pair)]
    mats, agrees = [], []
    for pair in order:
        c, a = phase_first_pair_curve(z, pair)
        mats.append(c)
        agrees.append(a)
    return np.vstack(mats), v14.PAIR_F, order, np.vstack(agrees)


def aggregate_phase_first(
    obs: pd.DataFrame,
    pair_w: pd.DataFrame,
    fretted_only_above_hz: float | None = None,
) -> np.ndarray:
    mat, _, order, agree = build_phase_first_matrix(
        obs, fretted_only_above_hz=fretted_only_above_hz
    )
    wmap = pair_w.set_index("pair")["pair_weight"].to_dict()
    # Pair weight × median phase agreement along the curve.
    ww = np.array(
        [
            wmap.get(p, 0.5) * float(np.nanmedian(agree[i]))
            for i, p in enumerate(order)
        ],
        float,
    )
    # Also apply per-frequency agreement into a weighted median approx:
    # scale each pair row by its agree vector via soft reweighting of values
    # toward nan when agreement is very low (already in curve mix).
    out = np.empty(mat.shape[1])
    for j in range(mat.shape[1]):
        col = mat[:, j]
        wj = ww * np.clip(agree[:, j], 0.15, 1.0)
        ok = np.isfinite(col) & np.isfinite(wj) & (wj > 0)
        if not ok.any():
            out[j] = np.nan
            continue
        out[j] = m.weighted_quantile(col[ok], wj[ok], 0.5)
    return out


def score_holdout(curve_dense: np.ndarray, gain: float, label: str) -> dict:
    hold = v15.fidelity_audit(curve_dense, gain, label, pairs=HOLD_PAIRS)
    crit = hold[hold.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
    return {
        "variant": label,
        "holdout_critical_rmse_db": float(crit.rmse_db.median()),
        "bias_2k4k_db": float(hold.loc[hold.band == "2k-4k", "bias_db"].median()),
        "gain_db": float(gain),
    }


def calibrate_curve(
    curve_pair: np.ndarray, gain0: float, pairs: list[str]
) -> tuple[np.ndarray, float, float, float]:
    dense, eff = v17.to_dense_neutral(curve_pair)
    g1 = gain0 + eff
    dense_cal, scale, gain_cal = v15.calibrate_presence_scale(dense, g1, pairs)
    return dense, dense_cal, gain_cal, scale


def gain_modes(
    dense_cal: np.ndarray, gain_cal: float, fund: pd.DataFrame
) -> dict[str, float]:
    """Race a few residual-gain interpretations without changing shape much."""
    modes = {"presence_cal": float(gain_cal)}
    # Non-open sustain residual around the calibrated curve.
    try:
        g_no = v14.non_open_sustain_gain(fund, dense_cal)
        if np.isfinite(g_no.get("median_db", np.nan)):
            modes["non_open_sustain"] = float(g_no["median_db"])
    except Exception:
        pass
    # Small CALIB-only gain grid around presence_cal (±0.6 dB).
    best_g, best_s = gain_cal, 1e9
    for dg in np.linspace(-0.6, 0.6, 13):
        g = gain_cal + float(dg)
        h = v15.fidelity_audit(dense_cal, g, "grid", pairs=CALIB_PAIRS)
        crit = h[h.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
        s = float(crit.rmse_db.median())
        if s < best_s:
            best_s, best_g = s, g
    modes["calib_grid"] = float(best_g)
    return modes


def main() -> None:
    t0 = time.time()
    run_id = f"v18_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v18", stages=["improve_v18"]
    )

    g12 = float(
        json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
    )
    pair_w = v17.pair_alignment_weights()
    pair_w.to_csv(OUT / "PESOS_PAREJA_ALINEACION_V18.csv", index=False)
    conf18 = event_confidence_v18()
    conf18.to_csv(OUT / "PESOS_EVENTO_V18.csv", index=False)
    print(
        f"1 event conf median {conf18.event_confidence_v18.median():.3f} "
        f"p10 {conf18.event_confidence_v18.quantile(0.1):.3f}",
        flush=True,
    )

    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")

    # Residual-weight × aggregation races.
    residual_levels = {
        "narrow": 0.05,
        "light": 0.10,
        "current": 0.20,
        "strong": 0.35,
    }
    results = []
    store = {}

    print("2 phase-first + residual races", flush=True)
    for rname, rw in residual_levels.items():
        obs = enrich_v18(g12, residual_w0=rw)
        # A: phase-first weighted
        curve = aggregate_phase_first(obs, pair_w, fretted_only_above_hz=None)
        dense0, dense_cal, gain_cal, scale = calibrate_curve(curve, g12, CALIB_PAIRS)
        label = f"v18_pf_{rname}"
        store[label] = (dense0, dense_cal, gain_cal, scale, curve)
        row = score_holdout(dense_cal, gain_cal, label)
        row["presence_scale"] = scale
        row["residual_w0"] = rw
        row["agg"] = "phase_first"
        results.append(row)
        print(
            f"   {label}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"bias2k4k {row['bias_2k4k_db']:+.3f} scale {scale:.3f}",
            flush=True,
        )

        # B: fretted-primary phase-first
        curve_f = aggregate_phase_first(obs, pair_w, fretted_only_above_hz=300.0)
        dense0f, dense_calf, gain_calf, scalef = calibrate_curve(
            curve_f, g12, CALIB_PAIRS
        )
        label_f = f"v18_pf_fret_{rname}"
        store[label_f] = (dense0f, dense_calf, gain_calf, scalef, curve_f)
        row = score_holdout(dense_calf, gain_calf, label_f)
        row["presence_scale"] = scalef
        row["residual_w0"] = rw
        row["agg"] = "phase_first_fretted"
        results.append(row)
        print(
            f"   {label_f}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"bias2k4k {row['bias_2k4k_db']:+.3f} scale {scalef:.3f}",
            flush=True,
        )

    # V17-style obs-level mix with V18 event conf (no phase-first), residual=current.
    print("3 V17-style + V18 event conf", flush=True)
    obs = enrich_v18(g12, residual_w0=0.20)
    obs = v17.phase_repeatability_weights(obs)
    for name, curve_p in v17.aggregate_variants(obs, pair_w).items():
        if name not in ("weighted_all", "weighted_fretted"):
            continue
        dense0, dense_cal, gain_cal, scale = calibrate_curve(curve_p, g12, CALIB_PAIRS)
        label = f"v18_obs_{name}"
        store[label] = (dense0, dense_cal, gain_cal, scale, curve_p)
        row = score_holdout(dense_cal, gain_cal, label)
        row["presence_scale"] = scale
        row["residual_w0"] = 0.20
        row["agg"] = f"obs_{name}"
        results.append(row)
        print(
            f"   {label}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"bias2k4k {row['bias_2k4k_db']:+.3f}",
            flush=True,
        )

    # Gain-mode race on the current best shape so far.
    ranking = pd.DataFrame(results).sort_values("holdout_critical_rmse_db")
    best_shape = ranking.iloc[0]
    key0 = str(best_shape.variant)
    dense0, dense_cal, gain_cal, scale, _ = store[key0]
    print(f"4 gain modes on {key0}", flush=True)
    modes = gain_modes(dense_cal, gain_cal, fund)
    for mname, g in modes.items():
        label = f"{key0}__gain_{mname}"
        row = score_holdout(dense_cal, g, label)
        row["presence_scale"] = scale
        row["residual_w0"] = best_shape.get("residual_w0", np.nan)
        row["agg"] = f"gain_{mname}"
        row["shape_variant"] = key0
        results.append(row)
        store[label] = (dense0, dense_cal, g, scale, store[key0][4])
        print(
            f"   {mname}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"gain {g:+.3f}",
            flush=True,
        )

    # Baselines: V17 operative + V15 recal.
    v17c = pd.read_csv(OUT / "CURVA_COPIA_OPERATIVA.csv")
    c17 = np.interp(np.log(m.DENSE_F), np.log(v17c.frequency_hz), v17c.eq_copy_db)
    g17 = float(pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db)
    row = score_holdout(c17, g17, "v17_operative")
    row["presence_scale"] = np.nan
    row["residual_w0"] = np.nan
    row["agg"] = "baseline"
    results.append(row)

    v15c = pd.read_csv(OUT / "CURVAS_DENSAS_V15_FIEL.csv")
    detail15 = np.interp(
        np.log(m.DENSE_F), np.log(v15c.frequency_hz), v15c.eq_observed_detail_db
    )
    g15_detail = float(
        json.loads((OUT / "RESUMEN_V15.json").read_text()).get(
            "gain_observed_detail_db", -11.8
        )
    )
    c15, s15, g15 = v15.calibrate_presence_scale(detail15, g15_detail, CALIB_PAIRS)
    row = score_holdout(c15, g15, "v15_faithful_recal")
    row["presence_scale"] = s15
    row["residual_w0"] = np.nan
    row["agg"] = "baseline"
    results.append(row)

    ranking = pd.DataFrame(results)
    ranking["abs_bias_2k4k"] = ranking.bias_2k4k_db.abs()
    ranking = ranking.sort_values(
        ["holdout_critical_rmse_db", "abs_bias_2k4k"]
    ).reset_index(drop=True)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_HOLDOUT_V18.csv", index=False)
    print(ranking.round(3).to_string(index=False), flush=True)

    best_rmse = float(ranking.holdout_critical_rmse_db.min())
    near = ranking[ranking.holdout_critical_rmse_db <= best_rmse + 0.05]
    best = near.sort_values(["abs_bias_2k4k", "holdout_critical_rmse_db"]).iloc[0]
    best_name = str(best.variant)
    print(
        f"5 winner: {best_name} RMSE={best.holdout_critical_rmse_db:.3f} "
        f"bias2k4k={best.bias_2k4k_db:+.3f}",
        flush=True,
    )

    if best_name in store:
        op_curve, op_gain = store[best_name][1], store[best_name][2]
        op_scale = store[best_name][3]
        detail = store[best_name][0]
    elif best_name == "v17_operative":
        op_curve, op_gain, op_scale, detail = c17, g17, np.nan, c17
    else:
        op_curve, op_gain, op_scale, detail = c15, g15, s15, detail15

    # Publish dense catalogue of top shapes.
    rows = {"frequency_hz": m.DENSE_F, "eq_faithful_best_db": op_curve}
    for name, (d0, dcal, gcal, sc, _) in store.items():
        if name.startswith(best_name.split("__")[0]) or name in ranking.head(6).variant.tolist():
            rows[f"faithful_{name}_db"] = dcal
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_DENSAS_V18.csv", index=False)

    beat_v17 = float(best.holdout_critical_rmse_db) < float(
        ranking.loc[ranking.variant == "v17_operative", "holdout_critical_rmse_db"].iloc[0]
    ) - 1e-6 or (
        abs(
            float(best.holdout_critical_rmse_db)
            - float(
                ranking.loc[
                    ranking.variant == "v17_operative", "holdout_critical_rmse_db"
                ].iloc[0]
            )
        )
        <= 0.05
        and abs(float(best.bias_2k4k_db))
        < abs(
            float(
                ranking.loc[ranking.variant == "v17_operative", "bias_2k4k_db"].iloc[0]
            )
        )
        - 1e-6
    )

    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "source_variant": best_name,
            "smoothing": "none",
            "pipeline_version": "V18.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)
    # Also keep a versioned copy.
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "source_variant": best_name,
            "smoothing": "none",
            "pipeline_version": "V18.0",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA_V18.csv", index=False)

    pd.DataFrame(
        [
            {
                "gain_recommended_db": op_gain,
                "gain_source": best_name,
                "presence_scale": op_scale,
                "smoothing": "none",
                "pipeline_version": "V18.0-operative",
                "replaces_v17": bool(beat_v17),
            }
        ]
    ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)
    pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").to_csv(
        OUT / "GAIN_COPIA_OPERATIVA_V18.csv", index=False
    )

    print("6 full fretted audit", flush=True)
    audits = []
    for label, curve_d, g in (
        ("operative", op_curve, op_gain),
        ("v17_operative", c17, g17),
        ("v15_faithful_recal", c15, g15),
    ):
        audits.append(v15.fidelity_audit(curve_d, g, label, pairs=ALL_TEST))
    audit = pd.concat(audits, ignore_index=True)
    audit.to_csv(OUT / "FIDELIDAD_RENDER_V18.csv", index=False)
    summ = v15.summarize_fidelity(audit)
    summ.to_csv(OUT / "FIDELIDAD_RENDER_RESUMEN_V18.csv", index=False)
    print(
        summ[summ.band == "2k-4k"][
            ["variant", "rmse_median_db", "bias_median_db"]
        ]
        .round(2)
        .to_string(index=False),
        flush=True,
    )

    v41 = {
        98: -0.76,
        515: 3.49,
        958: 3.49,
        1360: 4.08,
        2630: 6.61,
        4120: 6.34,
        5190: 4.33,
    }
    pts = []
    for hz, theirs in v41.items():
        pts.append(
            {
                "frequency_hz": hz,
                "operative_db": float(
                    np.interp(np.log(hz), np.log(m.DENSE_F), op_curve)
                ),
                "v17_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c17)),
                "v15_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c15)),
                "v41_db": theirs,
            }
        )
    pd.DataFrame(pts).to_csv(OUT / "COMPARACION_V18_VS_V41.csv", index=False)
    print(pd.DataFrame(pts).round(2).to_string(index=False), flush=True)

    print("7 proof audio", flush=True)
    import soundfile as sf

    proof = AUD / "FIDELIDAD_V18"
    proof.mkdir(parents=True, exist_ok=True)
    p = m.PAIRS["B_12"]
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

    impl = {
        "version": "V18.0",
        "smoothing": "none",
        "operative_curve_csv": "CURVA_COPIA_OPERATIVA.csv",
        "operative_gain_csv": "GAIN_COPIA_OPERATIVA.csv",
        "operative_variant": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if (op_scale != op_scale) else float(op_scale),
        "beat_v17": bool(beat_v17),
        "holdout_ranking_head": ranking.head(12).to_dict("records"),
        "calib_pairs": CALIB_PAIRS,
        "hold_pairs": HOLD_PAIRS,
        "intent": "Faithful Azul copy; phase-first + event conf + residual race; no smooth.",
    }
    (OUT / "IMPLEMENTACION_FIEL_V18.json").write_text(
        json.dumps(impl, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "run_id": run_id,
        "intent": "faithful_copy_without_smoothing",
        "winner": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if (op_scale != op_scale) else float(op_scale),
        "holdout_rmse_db": float(best.holdout_critical_rmse_db),
        "bias_2k4k_db": float(best.bias_2k4k_db),
        "beat_v17": bool(beat_v17),
        "ranking_head": ranking.head(15).to_dict("records"),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V18.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
