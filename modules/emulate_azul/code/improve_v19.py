"""V19: harden presence (2–6 kHz) without octave smoothing.

Diagnosis (existing 16 pairs): median Café+EQ vs Azul bias in presence is
near 0, but pairs disagree hard — C_12/B_12/G_12 overshoot, C_24/D_12 stay
dull. Global presence_scale≈0.38 damps everyone because outliers inflate the
raw curve.

V19 keeps V17's observation path and:

1. Builds per-pair curves (unsmoothed local median).
2. In the presence band, down-weights pairs with extreme deviations (robust).
3. Optionally blends lows from V17 flat/weighted with presence-robust shape.
4. Recalibrates a single presence scale on CALIB; scores HOLD.
5. Updates CURVA_COPIA_OPERATIVA only if hold-out improves (RMSE, then |bias|).
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
CALIB = v17.CALIB_PAIRS
HOLD = v17.HOLD_PAIRS
ALL_TEST = v17.ALL_TEST
PRES_LO, PRES_HI = 1500.0, 6500.0


def pair_curves(obs: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    z = obs[obs.w > 0]
    order = sorted(z.pair.unique())
    mats = [
        v14._local_median(
            z[z.pair == p].f,
            z[z.pair == p].y_timbre,
            z[z.pair == p].w,
            v14.PAIR_F,
            LOCAL_OCT,
        )
        for p in order
    ]
    return np.vstack(mats), order


def presence_band_mask(freq: np.ndarray = v14.PAIR_F) -> np.ndarray:
    return (freq >= PRES_LO) & (freq < PRES_HI)


def robust_pair_weights(mat: np.ndarray, base_w: np.ndarray, freq: np.ndarray) -> np.ndarray:
    """Per-frequency pair weights: base × presence-robust factor.

    Outside presence: base only.
    Inside presence: down-weight pairs far from the weighted median (MAD).
    """
    n, nf = mat.shape
    out = np.tile(base_w.reshape(-1, 1), (1, nf))
    pres = presence_band_mask(freq)
    # Global presence level per pair (median in band) for a stable outlier score.
    levels = []
    for i in range(n):
        col = mat[i, pres]
        levels.append(float(np.nanmedian(col)) if np.isfinite(col).any() else np.nan)
    levels = np.asarray(levels, float)
    ok = np.isfinite(levels) & (base_w > 0)
    if ok.sum() < 3:
        return out
    center = m.weighted_quantile(levels[ok], base_w[ok], 0.5)
    mad = 1.4826 * m.weighted_quantile(np.abs(levels[ok] - center), base_w[ok], 0.5)
    mad = max(mad, 0.75)  # dB floor
    # Tukey-ish: full weight within 1 MAD, zero by 3 MAD.
    z = np.abs(levels - center) / mad
    rob = np.clip(1.0 - (z - 1.0) / 2.0, 0.15, 1.0)
    rob = np.where(np.isfinite(levels), rob, 0.5)
    # Apply only in presence columns.
    out[:, pres] *= rob.reshape(-1, 1)
    return out


def weighted_median_rows(mat: np.ndarray, w_mat: np.ndarray) -> np.ndarray:
    out = np.empty(mat.shape[1])
    for j in range(mat.shape[1]):
        col = mat[:, j]
        w = w_mat[:, j]
        ok = np.isfinite(col) & np.isfinite(w) & (w > 0)
        out[j] = m.weighted_quantile(col[ok], w[ok], 0.5) if ok.any() else np.nan
    return out


def stitch_presence(
    low_curve: np.ndarray, pres_curve: np.ndarray, freq: np.ndarray
) -> np.ndarray:
    """Crossfade lows→presence over ~1/6 octave around PRES_LO/PRES_HI edges.

    Not regional EQ smoothing of the shape — only a short crossfade between
    two already-formed unsmoothed curves.
    """
    y = low_curve.copy()
    # Crossfade into presence
    lo0, lo1 = PRES_LO / (2 ** (1 / 12)), PRES_LO * (2 ** (1 / 12))
    hi0, hi1 = PRES_HI / (2 ** (1 / 12)), PRES_HI * (2 ** (1 / 12))
    for i, f in enumerate(freq):
        if lo0 <= f < lo1:
            t = (np.log(f) - np.log(lo0)) / (np.log(lo1) - np.log(lo0))
            y[i] = (1 - t) * low_curve[i] + t * pres_curve[i]
        elif lo1 <= f < hi0:
            y[i] = pres_curve[i]
        elif hi0 <= f < hi1:
            t = (np.log(f) - np.log(hi0)) / (np.log(hi1) - np.log(hi0))
            y[i] = (1 - t) * pres_curve[i] + t * low_curve[i]
    return y


def score_hold(curve_d: np.ndarray, gain: float, label: str) -> dict:
    hold = v15.fidelity_audit(curve_d, gain, label, pairs=HOLD)
    crit = hold[hold.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
    return {
        "variant": label,
        "holdout_critical_rmse_db": float(crit.rmse_db.median()),
        "bias_2k4k_db": float(hold.loc[hold.band == "2k-4k", "bias_db"].median()),
        "bias_1k2k_db": float(hold.loc[hold.band == "1k-2k", "bias_db"].median()),
        "gain_db": float(gain),
    }


def presence_error_table(curve_d: np.ndarray, gain: float) -> pd.DataFrame:
    bands = [
        (1000, 2000, "1k-2k"),
        (2000, 4000, "2k-4k"),
        (4000, 6000, "4k-6k"),
    ]
    h = m.fir_from_curve(curve_d)
    rows = []
    for key in ALL_TEST:
        if key not in m.PAIRS:
            continue
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        z = m.apply_eq(yc, h, gain)
        L = min(len(z), len(ya))
        f, Sz = v15.band_spectrum_db(z[:L], m.SR)
        _, Sa = v15.band_spectrum_db(ya[:L], m.SR)
        for lo, hi, name in bands:
            sel = (f >= lo) & (f < hi)
            err = Sz[sel] - Sa[sel]
            rows.append(
                {
                    "pair": key,
                    "band": name,
                    "bias_db": float(np.mean(err)),
                    "rmse_db": float(np.sqrt(np.mean(err**2))),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.time()
    run_id = f"v19_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v19", stages=["improve_v19"]
    )

    g12 = float(
        json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
    )
    print("1 observations (V15 path + V17 phase rep)", flush=True)
    obs = v15.enrich_observations(g12)
    obs = v17.phase_repeatability_weights(obs)
    pair_w = v17.pair_alignment_weights()
    wmap = pair_w.set_index("pair")["pair_weight"].to_dict()

    mat, order = pair_curves(obs)
    base_w = np.array([wmap.get(p, 0.5) for p in order], float)
    print("   pairs", order, flush=True)

    # Pair presence levels for diagnostics.
    pres = presence_band_mask()
    levels = np.array(
        [
            float(np.nanmedian(mat[i, pres])) if np.isfinite(mat[i, pres]).any() else np.nan
            for i in range(len(order))
        ]
    )
    lvl = pd.DataFrame({"pair": order, "presence_median_db": levels, "pair_weight": base_w})
    lvl.to_csv(OUT / "PRESENCIA_NIVELES_PAREJA_V19.csv", index=False)
    print(lvl.sort_values("presence_median_db").round(2).to_string(index=False), flush=True)

    w_rob = robust_pair_weights(mat, base_w, v14.PAIR_F)
    # Export effective presence weights.
    pd.DataFrame(
        {
            "pair": order,
            "w_base": base_w,
            "w_presence": w_rob[:, np.argmax(pres)],
            "presence_median_db": levels,
        }
    ).to_csv(OUT / "PESOS_PRESENCIA_ROBUSTOS_V19.csv", index=False)

    # Curves
    curve_flat = np.nanmedian(mat, axis=0)
    curve_w = v17.weighted_nanmedian(mat, base_w)
    curve_rob = weighted_median_rows(mat, w_rob)
    curve_stitch = stitch_presence(curve_w, curve_rob, v14.PAIR_F)

    # Fretted-only robust (open excluded entirely for shape)
    fretted = [i for i, p in enumerate(order) if not str(p).endswith("_open") and p not in ()]
    # Better: family from obs
    open_pairs = set(obs.loc[obs.family == "open", "pair"].unique())
    fret_idx = [i for i, p in enumerate(order) if p not in open_pairs]
    mat_f = mat[fret_idx]
    base_f = base_w[fret_idx]
    w_rob_f = robust_pair_weights(mat_f, base_f, v14.PAIR_F)
    curve_rob_f = weighted_median_rows(mat_f, w_rob_f)
    curve_stitch_f = stitch_presence(
        v17.weighted_nanmedian(mat_f, base_f), curve_rob_f, v14.PAIR_F
    )

    variants = {
        "v19_weighted": curve_w,
        "v19_presence_robust": curve_rob,
        "v19_stitch_w_rob": curve_stitch,
        "v19_fretted_presence_robust": curve_rob_f,
        "v19_stitch_fretted": curve_stitch_f,
        "v19_flat": curve_flat,
    }

    results = []
    store = {}
    print("2 calibrate + hold-out", flush=True)
    for name, curve_p in variants.items():
        ref = v12.cafe_reference_spectrum(v14.PAIR_F)
        neu, eff = v12.energy_neutralize(np.nan_to_num(curve_p, nan=0.0), ref)
        dense = v15.upsample_faithful(v14.PAIR_F, neu, m.DENSE_F)
        gain0 = g12 + eff
        dense_cal, scale, gain_cal = v15.calibrate_presence_scale(dense, gain0, CALIB)
        store[name] = (dense, dense_cal, gain_cal, scale)
        row = score_hold(dense_cal, gain_cal, name)
        row["presence_scale"] = scale
        results.append(row)
        print(
            f"   {name}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"bias2k4k {row['bias_2k4k_db']:+.3f} scale {scale:.3f}",
            flush=True,
        )

    # Baseline V17 operative
    v17c = pd.read_csv(OUT / "CURVA_COPIA_OPERATIVA.csv")
    c17 = np.interp(np.log(m.DENSE_F), np.log(v17c.frequency_hz), v17c.eq_copy_db)
    g17 = float(pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db)
    row = score_hold(c17, g17, "v17_operative")
    row["presence_scale"] = np.nan
    results.append(row)

    ranking = pd.DataFrame(results)
    ranking["abs_bias_2k4k"] = ranking.bias_2k4k_db.abs()
    ranking = ranking.sort_values(
        ["holdout_critical_rmse_db", "abs_bias_2k4k"]
    ).reset_index(drop=True)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_HOLDOUT_V19.csv", index=False)
    print(ranking.round(3).to_string(index=False), flush=True)

    best_rmse = float(ranking.holdout_critical_rmse_db.min())
    near = ranking[ranking.holdout_critical_rmse_db <= best_rmse + 0.05]
    best = near.sort_values(["abs_bias_2k4k", "holdout_critical_rmse_db"]).iloc[0]
    best_name = str(best.variant)
    print(
        f"3 winner: {best_name} RMSE={best.holdout_critical_rmse_db:.3f} "
        f"bias2k4k={best.bias_2k4k_db:+.3f}",
        flush=True,
    )

    if best_name == "v17_operative":
        op_curve, op_gain, op_scale = c17, g17, np.nan
    else:
        op_curve, op_gain, op_scale = store[best_name][1], store[best_name][2], store[best_name][3]

    # Presence diagnostics for winner + v17
    print("4 presence error tables", flush=True)
    diag = []
    for label, curve_d, g in (("operative", op_curve, op_gain), ("v17_operative", c17, g17)):
        d = presence_error_table(curve_d, g)
        d["variant"] = label
        diag.append(d)
    diag = pd.concat(diag, ignore_index=True)
    diag.to_csv(OUT / "DIAGNOSTICO_PRESENCIA_RENDER_V19.csv", index=False)
    summ = (
        diag.groupby(["variant", "band"], as_index=False)
        .agg(
            bias_median=("bias_db", "median"),
            rmse_median=("rmse_db", "median"),
            bias_mad=("bias_db", lambda s: float(1.4826 * np.median(np.abs(s - np.median(s))))),
        )
    )
    summ.to_csv(OUT / "DIAGNOSTICO_PRESENCIA_RESUMEN_V19.csv", index=False)
    print(summ.round(2).to_string(index=False), flush=True)

    # Publish
    rows = {"frequency_hz": m.DENSE_F, "eq_faithful_best_db": op_curve}
    for name, (d0, dcal, gcal, sc) in store.items():
        rows[f"detail_{name}_db"] = d0
        rows[f"faithful_{name}_db"] = dcal
    rows["v17_operative_db"] = c17
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_DENSAS_V19.csv", index=False)

    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "source_variant": best_name,
            "smoothing": "none",
            "pipeline_version": "V19.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)
    pd.DataFrame(
        [
            {
                "gain_recommended_db": op_gain,
                "gain_source": best_name,
                "presence_scale": op_scale,
                "smoothing": "none",
                "pipeline_version": "V19.0-operative",
            }
        ]
    ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)

    # Proof audio
    import soundfile as sf

    proof = AUD / "FIDELIDAD_V19"
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

    # Landmark compare
    v41 = {1360: 4.08, 2630: 6.61, 4120: 6.34, 5190: 4.33}
    pts = []
    for hz, theirs in v41.items():
        pts.append(
            {
                "frequency_hz": hz,
                "operative_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), op_curve)),
                "v17_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c17)),
                "v41_db": theirs,
            }
        )
    pd.DataFrame(pts).to_csv(OUT / "COMPARACION_V19_VS_V41.csv", index=False)
    print(pd.DataFrame(pts).round(2).to_string(index=False), flush=True)

    beat = best_name != "v17_operative"
    impl = {
        "version": "V19.0",
        "intent": "Robust presence aggregation without smoothing",
        "operative_variant": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if op_scale != op_scale else float(op_scale),
        "beat_v17": beat,
        "presence_band_hz": [PRES_LO, PRES_HI],
        "holdout_ranking": ranking.to_dict("records"),
        "note": (
            "Presence weakness was pair disagreement (C_12 bright / C_24 dull), "
            "not a uniformly low EQ. Robust pair weights target that."
        ),
    }
    (OUT / "IMPLEMENTACION_FIEL_V19.json").write_text(
        json.dumps(impl, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        "run_id": run_id,
        "winner": best_name,
        "gain_db": float(op_gain),
        "presence_scale": None if op_scale != op_scale else float(op_scale),
        "holdout_rmse_db": float(best.holdout_critical_rmse_db),
        "bias_2k4k_db": float(best.bias_2k4k_db),
        "beat_v17": beat,
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V19.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
