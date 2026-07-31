"""V22: repair pathological high-band shape (presence cliff).

Auto-audit of V21 operative found:

* peak ≈ +6 dB @ 2.6 kHz
* crosses 0 near 3.7 kHz
* ≈ −5 dB @ 8 kHz
* then hard air taper snaps to 0 @ 10 kHz

V20 was smooth (+3…+4.5 dB through 2–8 kHz, air→0). Pair curves on the
V21 extract show extreme fretted outliers (G_12/C_24/E_12 cliffs >18 dB;
C_12 +21 dB in 6–8 kHz). Hold-out picked fretted_presence_robust numerically
but the shape is not musically plausible.

V22:
1. Winsorize per-pair curves in 1.5–10 kHz before aggregation.
2. Stronger presence-robust pair weights.
3. Shape score: penalise (eq@2.6k − eq@8k) cliffs and negative 4–8 kHz shelves.
4. Race shape-safe variants; keep air hard_10k / soft if hold-out OK.
5. Optional stitch: V21 lows (<1.5 kHz) + repaired presence.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import AUD, OUT, MODULE, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v14 as v14  # noqa: E402
import improve_v15 as v15  # noqa: E402
import improve_v17 as v17  # noqa: E402
import improve_v19 as v19  # noqa: E402
import improve_v20 as v20  # noqa: E402
import run_manifest  # noqa: E402

CALIB = v17.CALIB_PAIRS
HOLD = v17.HOLD_PAIRS
PRES_LO, PRES_HI = 1500.0, 10000.0
WINSOR_DB = 8.0


def _at(curve: np.ndarray, hz: float, freq: np.ndarray = m.DENSE_F) -> float:
    return float(np.interp(np.log(hz), np.log(freq), curve))


def shape_metrics(curve: np.ndarray, freq: np.ndarray = m.DENSE_F) -> dict:
    e26 = _at(curve, 2600, freq)
    e40 = _at(curve, 4000, freq)
    e60 = _at(curve, 6000, freq)
    e80 = _at(curve, 8000, freq)
    e10 = _at(curve, 10000, freq)
    e15 = _at(curve, 15000, freq)
    cliff = e26 - e80
    # Negative shelf in brillo relative to presence peak.
    shelf = min(e40, e60, e80)
    # Discontinuity into air band.
    air_step = abs(e80 - e10)
    return {
        "eq_2k6": e26,
        "eq_4k": e40,
        "eq_6k": e60,
        "eq_8k": e80,
        "eq_10k": e10,
        "eq_15k": e15,
        "cliff_2k6_8k_db": cliff,
        "min_4k8k_db": shelf,
        "air_step_8k_10k_db": air_step,
        "shape_bad": bool(cliff > 5.0 and shelf < -1.5),
    }


def winsorize_presence(mat: np.ndarray, freq: np.ndarray, limit: float = WINSOR_DB) -> np.ndarray:
    out = mat.copy()
    sel = (freq >= PRES_LO) & (freq < PRES_HI)
    out[:, sel] = np.clip(out[:, sel], -limit, limit)
    return out


def robust_weights_tight(mat: np.ndarray, base_w: np.ndarray, freq: np.ndarray) -> np.ndarray:
    """Like V19 robust weights but tighter in presence/brillo (1.5–10 kHz)."""
    n, nf = mat.shape
    out = np.tile(base_w.reshape(-1, 1), (1, nf))
    pres = (freq >= PRES_LO) & (freq < PRES_HI)
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
    mad = max(mad, 0.5)
    z = np.abs(levels - center) / mad
    # Tighter Tukey: full within 0.75 MAD, zero by 2.25 MAD.
    rob = np.clip(1.0 - (z - 0.75) / 1.5, 0.05, 1.0)
    rob = np.where(np.isfinite(levels), rob, 0.3)
    out[:, pres] *= rob.reshape(-1, 1)
    return out


def stitch_lows_presence(
    low_curve: np.ndarray, pres_curve: np.ndarray, freq: np.ndarray, xover: float = 1500.0
) -> np.ndarray:
    y = low_curve.copy()
    lo0, lo1 = xover / (2 ** (1 / 8)), xover * (2 ** (1 / 8))
    for i, f in enumerate(freq):
        if f < lo0:
            y[i] = low_curve[i]
        elif f > lo1:
            y[i] = pres_curve[i]
        else:
            t = (np.log(f) - np.log(lo0)) / (np.log(lo1) - np.log(lo0))
            y[i] = (1 - t) * low_curve[i] + t * pres_curve[i]
    return y


def soft_floor_brillo(curve: np.ndarray, freq: np.ndarray, floor_db: float = -0.5) -> np.ndarray:
    """Prevent deep negative shelves in 4–8 kHz (shape repair, not octave smooth)."""
    y = curve.copy()
    sel = (freq >= 4000.0) & (freq < 8000.0)
    y[sel] = np.maximum(y[sel], floor_db)
    # Short crossfade 3.5–4 kHz and 8–9 kHz into the floor region.
    for a, b, use_floor in ((3500.0, 4000.0, True), (8000.0, 9000.0, False)):
        sel = (freq >= a) & (freq < b)
        t = (np.log(freq[sel]) - np.log(a)) / (np.log(b) - np.log(a))
        if use_floor:
            target = np.maximum(curve[sel], floor_db)
            y[sel] = (1 - t) * curve[sel] + t * target
        else:
            y[sel] = (1 - t) * np.maximum(curve[sel], floor_db) + t * curve[sel]
    return y


def score_row(curve: np.ndarray, gain: float, label: str) -> dict:
    row = v19.score_hold(curve, gain, label)
    sm = shape_metrics(curve)
    row.update(sm)
    # Combined objective: hold-out first, then shape.
    row["shape_penalty"] = max(0.0, sm["cliff_2k6_8k_db"] - 3.0) + max(
        0.0, -1.0 - sm["min_4k8k_db"]
    )
    return row


def main() -> None:
    t0 = time.time()
    run_id = f"v22_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v22", stages=["improve_v22"]
    )

    g12 = float(
        json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
    )
    print("1 enrich + pair matrix", flush=True)
    obs = v15.enrich_observations(g12)
    obs = v17.phase_repeatability_weights(obs)
    pair_w = v17.pair_alignment_weights()
    wmap = pair_w.set_index("pair")["pair_weight"].to_dict()
    mat0, order = v19.pair_curves(obs)
    base_w = np.array([wmap.get(p, 0.5) for p in order], float)
    open_pairs = set(obs.loc[obs.family == "open", "pair"].unique())
    fret_idx = [i for i, p in enumerate(order) if p not in open_pairs]

    # Audit current operative
    op = pd.read_csv(OUT / "CURVA_COPIA_OPERATIVA.csv")
    cur = np.interp(np.log(m.DENSE_F), np.log(op.frequency_hz), op.eq_copy_db)
    cur_g = float(pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db)
    audit = shape_metrics(cur)
    print("   current operative shape:", {k: round(v, 2) if isinstance(v, float) else v for k, v in audit.items()}, flush=True)

    mat_w = winsorize_presence(mat0, v14.PAIR_F)
    w_rob = v19.robust_pair_weights(mat_w, base_w, v14.PAIR_F)
    w_tight = robust_weights_tight(mat_w, base_w, v14.PAIR_F)

    curve_w = v17.weighted_nanmedian(mat_w, base_w)
    curve_rob = v19.weighted_median_rows(mat_w, w_rob)
    curve_tight = v19.weighted_median_rows(mat_w, w_tight)
    curve_f = v19.weighted_median_rows(mat_w[fret_idx], w_tight[fret_idx])

    # Low curve from all-pair winsorized weighted (stable under 1.5 kHz).
    low_ref = curve_w

    variants_p = {
        "v22_winsor_weighted": curve_w,
        "v22_winsor_robust": curve_rob,
        "v22_winsor_tight": curve_tight,
        "v22_winsor_fretted_tight": curve_f,
        "v22_stitch_low_tight": stitch_lows_presence(low_ref, curve_tight, v14.PAIR_F),
        "v22_stitch_low_robust": stitch_lows_presence(low_ref, curve_rob, v14.PAIR_F),
    }

    print("2 calibrate + shape-aware hold-out", flush=True)
    store = {}
    results = []
    for name, curve_p in variants_p.items():
        ref = v12.cafe_reference_spectrum(v14.PAIR_F)
        neu, eff = v12.energy_neutralize(np.nan_to_num(curve_p, nan=0.0), ref)
        dense = v15.upsample_faithful(v14.PAIR_F, neu, m.DENSE_F)
        gain0 = g12 + eff
        dense_cal, scale, gain_cal = v15.calibrate_presence_scale(
            dense, gain0, CALIB, scale_lo_hz=500.0, scale_hi_hz=8000.0
        )
        # Shape repair pass on brillo (after scale).
        dense_floor = soft_floor_brillo(dense_cal, m.DENSE_F, floor_db=-0.5)
        for tag, curve_d, g in (
            (name, dense_cal, gain_cal),
            (f"{name}_floor", dense_floor, gain_cal),
        ):
            # Re-neutralize after floor.
            ref_d = v12.cafe_reference_spectrum(m.DENSE_F)
            curve_n, eff2 = v12.energy_neutralize(curve_d, ref_d)
            g2 = g + eff2
            store[tag] = (curve_n, g2, scale)
            row = score_row(curve_n, g2, tag)
            row["presence_scale"] = scale
            results.append(row)
            print(
                f"   {tag}: RMSE {row['holdout_critical_rmse_db']:.3f} "
                f"cliff {row['cliff_2k6_8k_db']:+.2f} min4-8 {row['min_4k8k_db']:+.2f} "
                f"bad={row['shape_bad']}",
                flush=True,
            )

    # Reference: current V21 and baseline V20
    row = score_row(cur, cur_g, "v21_current")
    row["presence_scale"] = np.nan
    results.append(row)
    v20p = MODULE / "baselines" / "v20" / "CURVA_COPIA_OPERATIVA.csv"
    if v20p.exists():
        v20df = pd.read_csv(v20p)
        c20 = np.interp(np.log(m.DENSE_F), np.log(v20df.frequency_hz), v20df.eq_copy_db)
        g20 = float(pd.read_csv(MODULE / "baselines" / "v20" / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db)
        # Stitch V21-ish lows from winsor weighted with V20 highs.
        c_stitch_v20 = stitch_lows_presence(
            v15.upsample_faithful(v14.PAIR_F, low_ref, m.DENSE_F),
            c20,
            m.DENSE_F,
            xover=1800.0,
        )
        ref_d = v12.cafe_reference_spectrum(m.DENSE_F)
        c_stitch_v20, eff = v12.energy_neutralize(c_stitch_v20, ref_d)
        store["v22_stitch_v20_highs"] = (c_stitch_v20, g12 + eff, np.nan)
        row = score_row(c_stitch_v20, g12 + eff, "v22_stitch_v20_highs")
        row["presence_scale"] = np.nan
        results.append(row)
        row = score_row(c20, g20, "v20_baseline_ref")
        row["presence_scale"] = np.nan
        results.append(row)

    ranking = pd.DataFrame(results)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_FORMA_V22.csv", index=False)

    # Select only among v22_* candidates (refs are diagnostic).
    cand = ranking[ranking.variant.astype(str).str.startswith("v22_")].copy()
    ok = cand[~cand.shape_bad].copy()
    if not len(ok):
        ok = cand.copy()
        print("   WARNING: no shape-safe v22 variant; least-bad cliff", flush=True)
    best_rmse = float(ok.holdout_critical_rmse_db.min())
    near = ok[ok.holdout_critical_rmse_db <= best_rmse + 0.15].copy()
    near = near.sort_values(
        ["shape_penalty", "holdout_critical_rmse_db", "cliff_2k6_8k_db"]
    ).reset_index(drop=True)
    best = near.iloc[0]
    best_name = str(best.variant)
    print(
        f"3 shape-safe winner {best_name} RMSE={best.holdout_critical_rmse_db:.3f} "
        f"cliff={best.cliff_2k6_8k_db:+.2f} min4-8={best.min_4k8k_db:+.2f}",
        flush=True,
    )
    base_curve, base_gain, base_scale = store[best_name]

    print("4 air taper on shape-safe curve", flush=True)
    air_variants = {
        "v22_no_taper": base_curve,
        "v22_soft_8_15": v20.air_taper_soft(base_curve, m.DENSE_F, 8000, 15000),
        "v22_hard_10k": v20.air_taper_hard10k(base_curve, m.DENSE_F),
        "v22_aac_then_soft": v20.air_taper_aac_then_soft(base_curve, m.DENSE_F),
    }
    air_rows = []
    for name, curve in air_variants.items():
        r = v20.score(curve, base_gain, name, HOLD)
        sm = shape_metrics(curve)
        r.update(sm)
        air_rows.append(r)
    air_rank = pd.DataFrame(air_rows)
    air_rank.to_csv(OUT / "FIDELIDAD_RANKING_AIRE_V22.csv", index=False)
    base_rmse = float(air_rank.loc[air_rank.variant == "v22_no_taper", "holdout_critical_rmse_db"].iloc[0])
    ok_air = air_rank[air_rank.holdout_critical_rmse_db <= base_rmse + 0.05].copy()
    # Prefer hard/soft air zeroing when shape already OK below 8k.
    air_best = "v22_hard_10k" if "v22_hard_10k" in set(ok_air.variant) else str(
        ok_air.sort_values("eq_at_15k_db", key=lambda s: s.abs()).iloc[0].variant
    )
    op_curve = air_variants[air_best]
    air_row = ok_air.loc[ok_air.variant == air_best].iloc[0]
    print(
        f"   air {air_best} eq8k={_at(op_curve,8000):+.2f} eq10k={_at(op_curve,10000):+.2f} "
        f"eq15k={air_row.eq_at_15k_db:+.2f}",
        flush=True,
    )

    final_shape = shape_metrics(op_curve)
    src = f"{best_name}+{air_best}"
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "eq_before_air_taper_db": base_curve,
            "source_variant": src,
            "air_policy": air_best,
            "smoothing": "none",
            "pipeline_version": "V22.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)
    pd.DataFrame(
        [
            {
                "gain_recommended_db": base_gain,
                "gain_source": src,
                "presence_scale": None if base_scale != base_scale else float(base_scale),
                "air_policy": air_best,
                "smoothing": "none",
                "pipeline_version": "V22.0-operative",
            }
        ]
    ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)

    rows = {"frequency_hz": m.DENSE_F, "eq_before_air_db": base_curve}
    for name, curve in air_variants.items():
        rows[f"{name}_db"] = curve
    rows["eq_operative_db"] = op_curve
    rows["v21_previous_db"] = cur
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_FORMA_V22.csv", index=False)

    pts = []
    for hz in (1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 7000, 8000, 10000, 15000):
        pts.append(
            {
                "frequency_hz": hz,
                "v21_db": _at(cur, hz),
                "v22_db": _at(op_curve, hz),
                "v20_db": _at(
                    np.interp(
                        np.log(m.DENSE_F),
                        np.log(pd.read_csv(v20p).frequency_hz),
                        pd.read_csv(v20p).eq_copy_db,
                    ),
                    hz,
                )
                if v20p.exists()
                else np.nan,
            }
        )
    pd.DataFrame(pts).to_csv(OUT / "COMPARACION_AGUDOS_V22.csv", index=False)
    print(pd.DataFrame(pts).round(2).to_string(index=False), flush=True)

    import soundfile as sf

    proof = AUD / "FIDELIDAD_V22"
    proof.mkdir(parents=True, exist_ok=True)
    p = m.PAIRS["B_12"]
    yc, _ = m.load(p["cafe"])
    ya, _ = m.load(p["azul"])
    z = m.apply_eq(yc, m.fir_from_curve(op_curve), base_gain)
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
        "audit_v21": audit,
        "winner_presence": best_name,
        "winner_air": air_best,
        "gain_db": float(base_gain),
        "holdout_rmse_db": float(air_row.holdout_critical_rmse_db),
        "shape_final": final_shape,
        "ranking_head": ranking.sort_values(
            ["shape_penalty", "holdout_critical_rmse_db"]
        ).head(12).to_dict("records"),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V22.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "AUDITORIA_AGUDOS_V22.json").write_text(
        json.dumps(
            {
                "problem": "V21 fretted/presence curve cliff +5→−5 dB from 2.6–8 kHz; air snap 8→10k",
                "cause": "Extreme fretted pair outliers after V21 re-extract; hold-out ignored shape",
                "fix": "Winsorize ±8 dB in 1.5–10k, tighter robust weights, soft floor −0.5 in 4–8k, shape-aware race",
                "v21": audit,
                "v22": final_shape,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps({k: summary[k] for k in summary if k != "ranking_head"}, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
