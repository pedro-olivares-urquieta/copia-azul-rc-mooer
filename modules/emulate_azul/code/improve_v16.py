"""V16: tighter faithful Azul copy — still no smoothing.

Builds on V15 with the V4.1 ideas that improve *fidelity*, not smoothness:

1. **Per-pair scalar gain** removed before spectral aggregation (§24).
2. **Held-out band scales** above 500 Hz (shape kept; no octave kernel).
3. **Pair bootstrap CI** on the unsmoothed faithful curve.
4. **Residual gain after EQ** (§43–45), non-open sustain.
5. Fidelity reported on pairs **not** used for scale calibration.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import AUD, MANIFEST, OUT, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v14 as v14  # noqa: E402
import improve_v15 as v15  # noqa: E402
import run_manifest  # noqa: E402

# Localization only (bin neighborhood), NOT regional held-out smoothing.
LOCAL_OCT = 1.0 / 12.0

# Scale bands: piecewise gain on the EQ, preserves local detail inside each band.
SCALE_BANDS = [
    (500.0, 1000.0),
    (1000.0, 2000.0),
    (2000.0, 4000.0),
    (4000.0, 8000.0),
    (8000.0, 12000.0),
]

CALIB_PAIRS = ["A_12", "C_12", "E_12", "C_chromatic"]
HOLD_PAIRS = ["B_12", "D_12", "G_12", "C_24"]
ALL_FRETTED = CALIB_PAIRS + HOLD_PAIRS + ["C_open"]  # C_open only for gain stats

PAIR_ID_MAP = {
    "note_a__open": "A_open",
    "note_b__open": "B_open",
    "note_c__open": "C_open",
    "note_d__open": "D_open",
    "note_e__open": "E_open",
    "note_g__open": "G_open",
    "note_a__fret_12": "A_12",
    "note_b__fret_12": "B_12",
    "note_c__fret_12": "C_12",
    "note_d__fret_12": "D_12",
    "note_e__fret_12": "E_12",
    "note_g__fret_12": "G_12",
    "note_c__fret_24": "C_24",
    "chromatic_c__frets_1_25": "C_chromatic",
    "chord_am7": "Am7",
    "chord_cmaj7": "Cmaj7",
}


def pair_scalar_gains() -> pd.DataFrame:
    """Per-pair scalar level Azul−Café from active RMS (existing sessions)."""
    audio = pd.read_csv(OUT / "NIVELES_AUDIO_HEADROOM_V13.csv")
    rows = []
    for _, r in audio.iterrows():
        key = PAIR_ID_MAP.get(str(r.pair_id))
        if not key:
            continue
        rows.append(
            {
                "pair": key,
                "gain_rms_db": float(r.rms_active_delta_db),
                "gain_truepeak_db": float(r.true_peak_delta_db),
                "gain_lufs_proxy_db": float(r.lufs_proxy_delta_db),
            }
        )
    # Prefer RMS; also merge V11 bulk pair gains when present.
    out = pd.DataFrame(rows)
    if (OUT / "GAIN_POR_PAREJA_V11.csv").exists():
        g11 = pd.read_csv(OUT / "GAIN_POR_PAREJA_V11.csv")[["pair", "gain_db"]].rename(
            columns={"gain_db": "gain_fund_residual_db"}
        )
        out = out.merge(g11, on="pair", how="left")
    # Operational scalar for demeaning: audio RMS (instrument level under matched take).
    out["gain_scalar_db"] = out["gain_rms_db"]
    return out


def demeaned_observations(gain_global: float, pair_gains: pd.DataFrame) -> pd.DataFrame:
    """Like V15 enrich, but subtract **per-pair** scalar before shape aggregation."""
    obs = v15.enrich_observations(gain_global)
    gmap = pair_gains.set_index("pair")["gain_scalar_db"].to_dict()
    # Replace global demeaning on fundamentals: y_timbre = y - pair_gain.
    # enrich_observations already did y - gain_global for fundamentals; undo and redo.
    fund_mask = obs.kind == "fundamental"
    obs.loc[fund_mask, "y_timbre"] = obs.loc[fund_mask, "y_timbre"] + gain_global
    pair_g = obs["pair"].map(gmap)
    # Fallback to global when a pair lacks audio row.
    pair_g = pair_g.fillna(gain_global)
    obs.loc[fund_mask, "y_timbre"] = obs.loc[fund_mask, "y_timbre"] - pair_g[fund_mask]
    obs["pair_gain_scalar_db"] = pair_g
    return obs


def pair_first_detail(obs: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    obs = obs[obs.w > 0].copy()
    order = sorted(obs.pair.unique())
    mats = []
    for pair in order:
        g = obs[obs.pair == pair]
        mats.append(
            v14._local_median(g.f, g.y_timbre, g.w, v14.PAIR_F, sigma_oct=LOCAL_OCT)
        )
    mat = np.vstack(mats)
    with np.errstate(all="ignore"):
        across = np.nanmedian(mat, axis=0)
        mad = 1.4826 * np.nanmedian(np.abs(mat - across), axis=0)
        n_pairs = np.sum(np.isfinite(mat), axis=0)
    table = pd.DataFrame(
        {
            "frequency_hz": v14.PAIR_F,
            "eq_detail_db": across,
            "pair_mad_db": mad,
            "n_pairs": n_pairs,
        }
    )
    return table, mat, order


def bootstrap_curve(mat: np.ndarray, n_boot: int = 160, seed: int = 20260728):
    rng = np.random.default_rng(seed)
    n = mat.shape[0]
    boots = np.empty((n_boot, mat.shape[1]))
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = np.nanmedian(mat[idx], axis=0)
    return np.nanpercentile(boots, 2.5, axis=0), np.nanpercentile(boots, 97.5, axis=0)


def apply_band_scales(curve: np.ndarray, freq: np.ndarray, scales: dict[tuple, float]):
    out = np.asarray(curve, float).copy()
    for (lo, hi), s in scales.items():
        msk = (freq >= lo) & (freq < hi)
        out[msk] = out[msk] * s
    # Above last band: keep last scale.
    last = SCALE_BANDS[-1]
    if last in scales:
        out[freq >= last[1]] = out[freq >= last[1]] * scales[last]
    return out


def calibrate_presence_scale_heldout(
    curve_dense: np.ndarray,
    gain_db: float,
    calib_pairs: list[str],
) -> tuple[np.ndarray, float, float]:
    """Single scale above 500 Hz (no smooth), fit only on calib pairs.

    Greedy per-band scales collapsed to the floor and hurt hold-out fidelity;
    one global presence scale preserves relative detail and generalises better.
    """
    dense_cal, scale, gain_cal = v15.calibrate_presence_scale(
        curve_dense, gain_db, calib_pairs
    )
    return dense_cal, scale, gain_cal


def residual_gain_after_eq(curve_dense: np.ndarray, gain_db: float) -> dict:
    """V4.1 §43–45: raw sustain level vs applied gain (curve already neutral)."""
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    z = fund[
        (fund.phase == "sustain")
        & (fund.family != "open")
        & (fund.snr >= 10)
        & (fund.match_cost <= 2.8)
    ].copy()
    per_pair = z.groupby("pair").y.median()
    raw = float(per_pair.median())
    # After energy-neutral EQ, residual gain ≈ raw sustain median (should track gain_db).
    rng = np.random.default_rng(991)
    vals = per_pair.to_numpy(float)
    boots = [
        float(np.median(rng.choice(vals, size=len(vals), replace=True)))
        for _ in range(5000)
    ]
    return {
        "n_pairs": int(len(per_pair)),
        "raw_sustain_median_db": raw,
        "residual_gain_db": raw,
        "applied_gain_db": float(gain_db),
        "applied_minus_raw_db": float(gain_db) - raw,
        "bootstrap_p025_db": float(np.percentile(boots, 2.5)),
        "bootstrap_p975_db": float(np.percentile(boots, 97.5)),
        "pairs": {k: float(v) for k, v in per_pair.round(3).items()},
    }


def main() -> None:
    t0 = time.time()
    run_id = f"v16_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v16", stages=["improve_v16"]
    )

    g12 = float(json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"])
    print("1 per-pair scalar gains", flush=True)
    pair_gains = pair_scalar_gains()
    pair_gains.to_csv(OUT / "GAIN_ESCALAR_POR_PAREJA_V16.csv", index=False)
    print(
        pair_gains[["pair", "gain_scalar_db"]].round(2).to_string(index=False),
        flush=True,
    )
    global_scalar = float(pair_gains.gain_scalar_db.median())
    print(f"   median pair scalar {global_scalar:+.3f} dB", flush=True)

    print("2 demeaned observations + pair-first detail", flush=True)
    obs = demeaned_observations(g12, pair_gains)
    table, mat, order = pair_first_detail(obs)
    lo, hi = bootstrap_curve(mat)
    table["ci95_low_db"] = lo
    table["ci95_high_db"] = hi
    table["ci_width_db"] = hi - lo

    # Energy-neutral the detail curve (shape only; gain separate).
    ref_p = v12.cafe_reference_spectrum(v14.PAIR_F)
    detail_n, eff = v12.energy_neutralize(
        np.nan_to_num(table.eq_detail_db.to_numpy(float), nan=0.0), ref_p
    )
    gain_detail = global_scalar + eff
    table["eq_detail_neutral_db"] = detail_n
    table.to_csv(OUT / "CURVA_DETALLE_V16.csv", index=False)
    print(f"   detail energy effect {eff:+.3f} → gain_detail {gain_detail:+.3f}", flush=True)

    dense_detail = v15.upsample_faithful(v14.PAIR_F, detail_n, m.DENSE_F)

    print("3 held-out presence-scale calibration (no smooth)", flush=True)
    dense_cal, presence_scale, gain_cal = calibrate_presence_scale_heldout(
        dense_detail, gain_detail, CALIB_PAIRS
    )
    scale_rows = [
        {"low_hz": 500.0, "high_hz": 20000.0, "scale": presence_scale, "mode": "single_presence"}
    ]
    pd.DataFrame(scale_rows).to_csv(OUT / "ESCALAS_BANDA_V16.csv", index=False)
    print(f"   presence_scale={presence_scale:.3f} gain_cal={gain_cal:+.3f} dB", flush=True)

    # Primary export.
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_detail_db": dense_detail,
            "eq_faithful_db": dense_cal,
            "pipeline_version": "V16.0-faithful",
            "smoothing": "none",
        }
    ).to_csv(OUT / "CURVAS_DENSAS_V16_FIEL.csv", index=False)

    # PAIR_F view + bootstrap.
    cal_pair = v15.upsample_faithful(m.DENSE_F, dense_cal, v14.PAIR_F)
    out_pair = table.copy()
    out_pair["eq_faithful_db"] = cal_pair
    out_pair["pipeline_version"] = "V16.0-faithful"
    out_pair.to_csv(OUT / "CURVA_FIEL_V16.csv", index=False)

    print("4 residual gain after EQ", flush=True)
    resid = residual_gain_after_eq(dense_cal, gain_cal)
    (OUT / "GAIN_RESIDUAL_V16.json").write_text(
        json.dumps(resid, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in resid.items() if k != "pairs"}, indent=2),
        flush=True,
    )

    print("5 fidelity on HOLD pairs (unseen by scale calib)", flush=True)
    v12c = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
    c12 = np.interp(np.log(m.DENSE_F), np.log(v12c.frequency_hz), v12c.energy_neutral_db)
    if (OUT / "CURVAS_DENSAS_V15_FIEL.csv").exists():
        v15c = pd.read_csv(OUT / "CURVAS_DENSAS_V15_FIEL.csv")
        c15 = np.interp(np.log(m.DENSE_F), np.log(v15c.frequency_hz), v15c.eq_faithful_db)
        g15 = float(json.loads((OUT / "RESUMEN_V15.json").read_text())["gain_faithful_db"])
    else:
        c15, g15 = c12, g12

    audits = []
    for label, curve_d, g in (
        ("v12_energy_neutral", c12, g12),
        ("v15_faithful", c15, g15),
        ("v16_detail", dense_detail, gain_detail),
        ("v16_faithful", dense_cal, gain_cal),
    ):
        audits.append(v15.fidelity_audit(curve_d, g, label, pairs=HOLD_PAIRS))
        # Also full fretted for comparison table.
        audits.append(
            v15.fidelity_audit(
                curve_d, g, label + "_all", pairs=["A_12", "B_12", "C_12", "D_12", "E_12", "G_12", "C_24", "C_chromatic"]
            )
        )
    audit = pd.concat(audits, ignore_index=True)
    audit.to_csv(OUT / "FIDELIDAD_RENDER_V16.csv", index=False)
    summary_fid = v15.summarize_fidelity(audit)
    summary_fid.to_csv(OUT / "FIDELIDAD_RENDER_RESUMEN_V16.csv", index=False)

    hold = summary_fid[summary_fid.variant.isin(
        ["v12_energy_neutral", "v15_faithful", "v16_detail", "v16_faithful"]
    )]
    crit = hold[hold.band.isin(["500-1k", "1k-2k", "2k-4k", "4k-8k"])]
    ranking = (
        crit.groupby("variant")
        .rmse_median_db.median()
        .sort_values()
        .rename("holdout_critical_rmse_db")
        .reset_index()
    )
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_HOLDOUT_V16.csv", index=False)
    print(ranking.round(3).to_string(index=False), flush=True)
    print(
        hold[hold.band == "2k-4k"][
            ["variant", "rmse_median_db", "bias_median_db"]
        ]
        .round(2)
        .to_string(index=False),
        flush=True,
    )

    # Checkpoints.
    v41 = {98: -0.76, 515: 3.49, 958: 3.49, 1360: 4.08, 2630: 6.61, 4120: 6.34, 5190: 4.33}
    pts = []
    for hz, theirs in v41.items():
        pts.append(
            {
                "frequency_hz": hz,
                "v16_detail_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), dense_detail)),
                "v16_faithful_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), dense_cal)),
                "v15_faithful_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c15)),
                "v12_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), c12)),
                "v41_db": theirs,
            }
        )
    pts_df = pd.DataFrame(pts)
    pts_df.to_csv(OUT / "COMPARACION_V16_VS_V41.csv", index=False)
    print(pts_df.round(2).to_string(index=False), flush=True)

    print("6 implementation package + proof audio", flush=True)
    # Operational copy = hold-out winner (honest selection).
    winner = ranking.iloc[0]["variant"]
    if winner == "v15_faithful":
        op_curve, op_gain, op_src = c15, g15, "CURVAS_DENSAS_V15_FIEL.csv::eq_faithful_db"
    elif winner == "v16_faithful":
        op_curve, op_gain, op_src = dense_cal, gain_cal, "CURVAS_DENSAS_V16_FIEL.csv::eq_faithful_db"
    elif winner == "v12_energy_neutral":
        op_curve, op_gain, op_src = c12, g12, "CURVAS_DENSAS_V12.csv::energy_neutral_db"
    else:
        op_curve, op_gain, op_src = dense_cal, gain_cal, "CURVAS_DENSAS_V16_FIEL.csv::eq_faithful_db"
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "source_variant": winner,
            "smoothing": "none",
            "pipeline_version": "V16.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)

    impl = {
        "version": "V16.0-faithful",
        "smoothing": "none",
        "operative_curve_csv": "CURVA_COPIA_OPERATIVA.csv",
        "operative_column": "eq_copy_db",
        "operative_source": op_src,
        "operative_variant": winner,
        "gain_db": float(op_gain),
        "v16_curve_csv": "CURVAS_DENSAS_V16_FIEL.csv",
        "v16_gain_db": gain_cal,
        "gain_residual_after_eq_db": resid["residual_gain_db"],
        "gain_ci95_db": [resid["bootstrap_p025_db"], resid["bootstrap_p975_db"]],
        "presence_scale": presence_scale,
        "band_scales": scale_rows,
        "per_pair_scalar": "GAIN_ESCALAR_POR_PAREJA_V16.csv",
        "holdout_pairs": HOLD_PAIRS,
        "calib_pairs": CALIB_PAIRS,
        "intent": "Copy Azul faithfully from existing 16-pair evidence without octave smoothing.",
    }
    (OUT / "IMPLEMENTACION_FIEL_V16.json").write_text(
        json.dumps(impl, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    import soundfile as sf

    proof = AUD / "FIDELIDAD_V16"
    proof.mkdir(parents=True, exist_ok=True)
    key = "B_12"  # hold-out pair
    p = m.PAIRS[key]
    yc, _ = m.load(p["cafe"])
    ya, _ = m.load(p["azul"])
    z16 = m.apply_eq(yc, m.fir_from_curve(dense_cal), gain_cal)
    z15 = m.apply_eq(yc, m.fir_from_curve(c15), g15)
    z12 = m.apply_eq(yc, m.fir_from_curve(c12), g12)
    zop = m.apply_eq(yc, m.fir_from_curve(op_curve), op_gain)
    L = min(len(z16), len(z15), len(z12), len(zop), len(ya))
    sf.write(proof / "AZUL_ORIGINAL.flac", ya[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_V16_FIEL.flac", z16[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_V15_FIEL.flac", z15[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_V12_NEUTRAL.flac", z12[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_COPIA_OPERATIVA.flac", zop[:L], m.SR, subtype="PCM_24")
    sf.write(
        proof / "ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac",
        np.column_stack([zop[:L], ya[:L]]),
        m.SR,
        subtype="PCM_24",
    )

    summary = {
        "run_id": run_id,
        "intent": "faithful_copy_without_smoothing",
        "primary": "CURVAS_DENSAS_V16_FIEL.csv::eq_faithful_db",
        "gain_faithful_db": gain_cal,
        "gain_detail_db": gain_detail,
        "gain_residual_db": resid["residual_gain_db"],
        "median_pair_scalar_db": global_scalar,
        "presence_scale": presence_scale,
        "band_scales": scale_rows,
        "holdout_ranking": ranking.to_dict("records"),
        "best_holdout": ranking.iloc[0].to_dict(),
        "median_ci_width_db": float(np.nanmedian(table.ci_width_db)),
        "checkpoints": pts_df.to_dict("records"),
        "recommended_for_copy": (
            "v16_faithful"
            if ranking.iloc[0]["variant"] == "v16_faithful"
            else ranking.iloc[0]["variant"]
        ),
        "note": (
            "No octave smoothing. Per-pair RMS scalar removed before shape. "
            "Single presence scale calibrated on CALIB_PAIRS; fidelity ranked on HOLD_PAIRS. "
            "If hold-out prefers v15_faithful, keep that as operational copy."
        ),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V16.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
