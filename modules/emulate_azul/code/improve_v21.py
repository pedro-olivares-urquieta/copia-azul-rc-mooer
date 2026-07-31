"""V21: apply low-band + high-band audit fixes without smooth/shrink.

From ANALISIS_BAJOS_25_900_V41 + ANALISIS_PRESENCIA_BRILLO_AIRE_V41:

Lows (needs rebuild_v10_2 extract):
  * dedicated ``low`` window 60–760 ms (min 180 → sustain fallback)
  * linear detrend + pre-onset noise subtraction on PSD
  * real ``rel_db`` vs event peak (−58/−68/−82)
  * PHASE_MIX puts 82%/38% on ``low`` under 120 / 120–350
  * SNR split 350–600 / 600–900; mains σ=28¢

Highs:
  * ``presence_scale`` only on 0.5–8 kHz (not air)
  * keep V20 air taper race (hard_10k / AAC / soft)

Still refused: octave smooth, EQ×reliability, fixed ×0.62/0.55.
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
import improve_v19 as v19  # noqa: E402
import improve_v20 as v20  # noqa: E402
import run_manifest  # noqa: E402

CALIB = v17.CALIB_PAIRS
HOLD = v17.HOLD_PAIRS
CRIT = ["500-1k", "1k-2k", "2k-4k", "4k-8k"]


def _landmarks(curve: np.ndarray) -> dict[str, float]:
    out = {}
    for hz in (30.87, 55, 98, 220, 350, 400, 515, 900, 2500, 4000, 8000, 10000, 15000, 18000):
        out[f"{hz:g}"] = float(np.interp(np.log(hz), np.log(m.DENSE_F), curve))
    return out


def main() -> None:
    t0 = time.time()
    run_id = f"v21_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v21", stages=["improve_v21"]
    )

    g12 = float(
        json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
    )
    print("1 enrich observations (V21 weights: low/rel/hum/snr)", flush=True)
    obs = v15.enrich_observations(g12)
    obs = v17.phase_repeatability_weights(obs)
    n_low = int((obs.phase == "low").sum())
    has_rel = "rel_db" in obs.columns and np.isfinite(obs.rel_db).any()
    med_low_ms = float(
        obs.loc[obs.phase == "low", "duration_s"].median() * 1000
        if n_low
        else float("nan")
    )
    print(
        f"   low-phase rows={n_low} median_low_ms={med_low_ms:.1f} "
        f"rel_db_present={has_rel} mains_sigma={v12.MAINS_SIGMA_CENTS}",
        flush=True,
    )

    pair_w = v17.pair_alignment_weights()
    wmap = pair_w.set_index("pair")["pair_weight"].to_dict()
    mat, order = v19.pair_curves(obs)
    base_w = np.array([wmap.get(p, 0.5) for p in order], float)
    w_rob = v19.robust_pair_weights(mat, base_w, v14.PAIR_F)

    curve_w = v17.weighted_nanmedian(mat, base_w)
    curve_rob = v19.weighted_median_rows(mat, w_rob)
    curve_stitch = v19.stitch_presence(curve_w, curve_rob, v14.PAIR_F)
    open_pairs = set(obs.loc[obs.family == "open", "pair"].unique())
    fret_idx = [i for i, p in enumerate(order) if p not in open_pairs]
    mat_f, base_f = mat[fret_idx], base_w[fret_idx]
    w_rob_f = v19.robust_pair_weights(mat_f, base_f, v14.PAIR_F)
    curve_rob_f = v19.weighted_median_rows(mat_f, w_rob_f)

    variants = {
        "v21_weighted": curve_w,
        "v21_presence_robust": curve_rob,
        "v21_stitch_w_rob": curve_stitch,
        "v21_fretted_presence_robust": curve_rob_f,
    }

    print("2 calibrate presence 0.5–8 kHz + hold-out", flush=True)
    store = {}
    results = []
    for name, curve_p in variants.items():
        ref = v12.cafe_reference_spectrum(v14.PAIR_F)
        neu, eff = v12.energy_neutralize(np.nan_to_num(curve_p, nan=0.0), ref)
        dense = v15.upsample_faithful(v14.PAIR_F, neu, m.DENSE_F)
        gain0 = g12 + eff
        dense_cal, scale, gain_cal = v15.calibrate_presence_scale(
            dense, gain0, CALIB, scale_lo_hz=500.0, scale_hi_hz=8000.0
        )
        store[name] = (dense_cal, gain_cal, scale)
        row = v19.score_hold(dense_cal, gain_cal, name)
        row["presence_scale"] = scale
        results.append(row)
        print(
            f"   {name}: RMSE {row['holdout_critical_rmse_db']:.3f} "
            f"b2k4k {row['bias_2k4k_db']:+.3f} scale {scale:.3f}",
            flush=True,
        )

    ranking = pd.DataFrame(results)
    ranking["abs_bias_2k4k"] = ranking.bias_2k4k_db.abs()
    ranking = ranking.sort_values(
        ["holdout_critical_rmse_db", "abs_bias_2k4k"]
    ).reset_index(drop=True)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_HOLDOUT_V21.csv", index=False)
    best = ranking.iloc[0]
    best_name = str(best.variant)
    base_curve, base_gain, base_scale = store[best_name]
    print(
        f"3 presence winner {best_name} RMSE={best.holdout_critical_rmse_db:.3f}",
        flush=True,
    )

    print("4 air taper race (V20 policies)", flush=True)
    air_variants = {
        "v21_no_taper": base_curve,
        "v21_aac_prior": v20.air_taper_aac(base_curve, m.DENSE_F),
        "v21_soft_8_15": v20.air_taper_soft(base_curve, m.DENSE_F, 8000, 15000),
        "v21_hard_10k": v20.air_taper_hard10k(base_curve, m.DENSE_F),
        "v21_aac_then_soft": v20.air_taper_aac_then_soft(base_curve, m.DENSE_F),
    }
    air_rows = []
    for name, curve in air_variants.items():
        air_rows.append(v20.score(curve, base_gain, name, HOLD))
    air_rank = pd.DataFrame(air_rows)
    air_rank.to_csv(OUT / "FIDELIDAD_RANKING_AIRE_V21.csv", index=False)
    base_rmse = float(
        air_rank.loc[air_rank.variant == "v21_no_taper", "holdout_critical_rmse_db"].iloc[0]
    )
    ok = air_rank[
        air_rank.variant.str.startswith("v21_")
        & (air_rank.holdout_critical_rmse_db <= base_rmse + 0.05)
    ].copy()
    ok["abs_b8"] = ok.bias_8k12k_db.abs()
    ok["abs_eq15"] = ok.eq_at_15k_db.abs()
    ok = ok.sort_values(["abs_b8", "abs_eq15", "holdout_critical_rmse_db"]).reset_index(
        drop=True
    )
    air_best = str(ok.iloc[0].variant)
    op_curve = air_variants[air_best]
    print(
        f"   air winner {air_best} critRMSE={ok.iloc[0].holdout_critical_rmse_db:.3f} "
        f"eq15k={ok.iloc[0].eq_at_15k_db:+.2f}",
        flush=True,
    )

    # Optional: keep prior V20 operative if V21 hold-out is worse by >0.08.
    prev_path = OUT / "CURVA_COPIA_OPERATIVA.csv"
    keep_prev = False
    prev_rmse = np.nan
    if prev_path.exists():
        prev = pd.read_csv(prev_path)
        prev_c = np.interp(np.log(m.DENSE_F), np.log(prev.frequency_hz), prev.eq_copy_db)
        prev_g = float(
            pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db
        )
        prev_row = v20.score(prev_c, prev_g, "previous_operative", HOLD)
        prev_rmse = float(prev_row["holdout_critical_rmse_db"])
        new_rmse = float(ok.iloc[0].holdout_critical_rmse_db)
        if new_rmse > prev_rmse + 0.08:
            keep_prev = True
            print(
                f"5 KEEP previous operative (V21 RMSE {new_rmse:.3f} > prev {prev_rmse:.3f}+0.08)",
                flush=True,
            )

    if not keep_prev:
        src = f"{best_name}+{air_best}"
        pd.DataFrame(
            {
                "frequency_hz": m.DENSE_F,
                "eq_copy_db": op_curve,
                "eq_before_air_taper_db": base_curve,
                "source_variant": src,
                "air_policy": air_best,
                "smoothing": "none",
                "pipeline_version": "V21.0-operative",
            }
        ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)
        pd.DataFrame(
            [
                {
                    "gain_recommended_db": base_gain,
                    "gain_source": src,
                    "presence_scale": base_scale,
                    "air_policy": air_best,
                    "smoothing": "none",
                    "pipeline_version": "V21.0-operative",
                }
            ]
        ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)
        print(f"5 published operative {src} gain={base_gain:+.3f}", flush=True)
    else:
        src = str(pd.read_csv(prev_path).source_variant.iloc[0])
        op_curve = np.interp(
            np.log(m.DENSE_F),
            np.log(pd.read_csv(prev_path).frequency_hz),
            pd.read_csv(prev_path).eq_copy_db,
        )
        base_gain = float(
            pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db
        )
        air_best = "kept_previous"
        best_name = src

    rows = {"frequency_hz": m.DENSE_F, "eq_before_air_db": base_curve}
    for name, curve in air_variants.items():
        rows[f"{name}_db"] = curve
    rows["eq_operative_db"] = op_curve
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_V21.csv", index=False)

    pd.DataFrame(
        [{"frequency_hz": float(k), "eq_db": v} for k, v in _landmarks(op_curve).items()]
    ).to_csv(OUT / "LANDMARKS_V21.csv", index=False)

    import soundfile as sf

    proof = AUD / "FIDELIDAD_V21"
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

    checklist = {
        "low_window_60_760": n_low > 0,
        "median_low_duration_ms": med_low_ms,
        "rel_db_in_observations": has_rel,
        "mains_sigma_cents": v12.MAINS_SIGMA_CENTS,
        "snr_split_600_900": True,
        "presence_scale_band_hz": [500, 8000],
        "air_policy": air_best,
        "refused": [
            "octave_smooth_operative",
            "eq_times_reliability",
            "fixed_physical_multipliers",
        ],
    }
    (OUT / "CHECKLIST_AUDITORIAS_V21.json").write_text(
        json.dumps(checklist, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "run_id": run_id,
        "winner_presence": best_name,
        "winner_air": air_best,
        "kept_previous": keep_prev,
        "gain_db": float(base_gain),
        "presence_scale": float(base_scale) if not keep_prev else None,
        "holdout_rmse_db": float(ok.iloc[0].holdout_critical_rmse_db)
        if not keep_prev
        else prev_rmse,
        "previous_holdout_rmse_db": prev_rmse,
        "landmarks_db": _landmarks(op_curve),
        "checklist": checklist,
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V21.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "IMPLEMENTACION_FIEL_V21.json").write_text(
        json.dumps(
            {
                "version": "V21.0",
                "intent": "Apply low+high audit fixes; faithful copy without smooth/shrink",
                "operative_curve_csv": "CURVA_COPIA_OPERATIVA.csv",
                "pipeline_version": "V21.0-operative" if not keep_prev else "kept_previous",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
