"""V13: publish remaining validation surfaces demanded by the master prompt.

Runs against already-extracted V10.2 / V11 / V12 artifacts. Does not overwrite
the published baseline and does not refit the main Café→Azul curve.

Deliverables
------------
§13  Dense attack / sustain / phase curves (and multiscale attack summary).
§19  Deep gain catalogue: many estimators + true-peak / headroom / loudness.
§25  Leave-one-register-out, leave-one-pair-out, leave-one-exercise-out.
§22  Named curve aliases for the phase deliverables.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy import stats

from repo_paths import MANIFEST, OUT, REPO, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v11 as v11  # noqa: E402
import run_config  # noqa: E402
import run_manifest  # noqa: E402

PHASES = ["attack", "stabilization", "body", "sustain", "decay"]
KERNEL_SIGMA_OCT = 1.0 / 6.0  # ~2 semitones


def _load_obs() -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()
    res["weight_base"] *= 0.35
    obs = fund.to_dict("records") + ton.to_dict("records") + res.to_dict("records")
    return obs, fund, ton


def _local_curve(f_obs: np.ndarray, y_obs: np.ndarray, w_obs: np.ndarray, grid: np.ndarray):
    """Gaussian kernel weighted median on a log-frequency grid."""
    f_obs = np.asarray(f_obs, float)
    y_obs = np.asarray(y_obs, float)
    w_obs = np.asarray(w_obs, float)
    ok = np.isfinite(f_obs) & np.isfinite(y_obs) & np.isfinite(w_obs) & (w_obs > 0) & (f_obs > 0)
    f_obs, y_obs, w_obs = f_obs[ok], y_obs[ok], w_obs[ok]
    if not len(f_obs):
        return np.full(len(grid), np.nan), np.zeros(len(grid)), np.zeros(len(grid))

    ln = np.log2(f_obs)
    lng = np.log2(grid)
    med = np.empty(len(grid))
    n_eff = np.empty(len(grid))
    pair_proxy = np.empty(len(grid))
    for i, c in enumerate(lng):
        w = w_obs * np.exp(-0.5 * ((ln - c) / KERNEL_SIGMA_OCT) ** 2)
        keep = w > 1e-6 * w.max()
        if not keep.any():
            med[i] = np.nan
            n_eff[i] = 0.0
            pair_proxy[i] = 0.0
            continue
        ww = w[keep]
        yy = y_obs[keep]
        med[i] = m.weighted_quantile(yy, ww, 0.5)
        n_eff[i] = float((ww.sum() ** 2) / max((ww**2).sum(), 1e-30))  # Kish
        pair_proxy[i] = float(n_eff[i])
    return med, n_eff, pair_proxy


def publish_phase_curves(fund: pd.DataFrame, ton: pd.DataFrame, gain_db: float) -> pd.DataFrame:
    """Dense curves per envelope phase, level-separated from the global gain."""
    frames = []
    for src, kind_w in ((fund, 1.0), (ton, 0.55)):
        z = src.copy()
        z["w"] = z.weight_base * np.clip((z.snr - 6.0) / 24.0, 0.08, 1.5) * kind_w
        # Fundamentals carry absolute level; subtract gain so the phase curve is timbre.
        if "kind" not in z.columns or (z.kind == "fundamental").all():
            z["y_timbre"] = z.y - gain_db
        else:
            # Harmonic observations are already relative (Azul-Café of partials).
            z["y_timbre"] = z.y
        frames.append(z[["phase", "f", "y_timbre", "w", "pair", "snr"]])
    all_obs = pd.concat(frames, ignore_index=True)

    cols = {"frequency_hz": m.DENSE_F}
    support_rows = []
    for ph in PHASES:
        z = all_obs[all_obs.phase == ph]
        curve, n_eff, _ = _local_curve(z.f.to_numpy(), z.y_timbre.to_numpy(), z.w.to_numpy(), m.DENSE_F)
        cols[f"{ph}_db"] = curve
        cols[f"{ph}_n_eff"] = n_eff
        support_rows.append(
            {
                "phase": ph,
                "n_observations": int(len(z)),
                "n_pairs": int(z.pair.nunique()) if len(z) else 0,
                "median_snr_db": float(z.snr.median()) if len(z) else float("nan"),
                "fraction_finite_curve": float(np.isfinite(curve).mean()),
            }
        )

    out = pd.DataFrame(cols)
    # Relative-to-body diagnostics: what the static EQ cannot capture.
    body = out["body_db"].to_numpy(float)
    for ph in ("attack", "stabilization", "sustain", "decay"):
        out[f"{ph}_minus_body_db"] = out[f"{ph}_db"] - body

    out["pipeline_version"] = "V13.0"
    out.to_csv(OUT / "CURVAS_POR_FASE_V13.csv", index=False)

    # Named §22 aliases.
    aliases = (
        ("CURVA_ATAQUE_V13.csv", "attack_db", "attack_n_eff"),
        ("CURVA_SUSTAIN_V13.csv", "sustain_db", "sustain_n_eff"),
        ("CURVA_CUERPO_V13.csv", "body_db", "body_n_eff"),
        ("CURVA_ATAQUE_MENOS_CUERPO_V13.csv", "attack_minus_body_db", "attack_n_eff"),
        ("CURVA_SUSTAIN_MENOS_CUERPO_V13.csv", "sustain_minus_body_db", "sustain_n_eff"),
    )
    for name, value_col, neff_col in aliases:
        slim = out[["frequency_hz", value_col, neff_col]].rename(
            columns={value_col: "delta_db", neff_col: "n_eff"}
        )
        slim.to_csv(OUT / name, index=False)

    pd.DataFrame(support_rows).to_csv(OUT / "SOPORTE_CURVAS_FASE_V13.csv", index=False)
    return out


def publish_attack_multiscale() -> pd.DataFrame:
    """Collapse the multiscale attack map into a publishable band×window table."""
    att = pd.read_csv(OUT / "ATAQUES_MULTIESCALA_V10_2.csv")
    g = (
        att.groupby(["window", "band"], as_index=False)
        .agg(
            median_db=("delta_db", "median"),
            mad_db=("delta_db", lambda x: float(1.4826 * np.median(np.abs(x - np.median(x))))),
            p16_db=("delta_db", lambda x: float(np.percentile(x, 16))),
            p84_db=("delta_db", lambda x: float(np.percentile(x, 84))),
            n=("delta_db", "size"),
            n_pairs=("pair", "nunique"),
        )
    )
    g["pipeline_version"] = "V13.0"
    g.to_csv(OUT / "CURVA_ATAQUE_MULTIESCALA_V13.csv", index=False)
    return g


def _active_mask(y: np.ndarray, sr: int, floor_frac: float = 0.05) -> np.ndarray:
    n = max(int(0.02 * sr), 1)
    fr = y[: len(y) // n * n].reshape(-1, n)
    e = np.sqrt(np.mean(fr**2, axis=1))
    thr = floor_frac * e.max() if e.max() > 0 else 0.0
    active_frames = e > max(thr, 1e-8)
    mask = np.repeat(active_frames, n)
    if len(mask) < len(y):
        mask = np.r_[mask, np.zeros(len(y) - len(mask), dtype=bool)]
    return mask.astype(bool)


def _true_peak_dbfs(y: np.ndarray, sr: int) -> float:
    """4× polyphase peak estimate (simple true-peak proxy)."""
    if len(y) < 8:
        return float(20 * np.log10(max(np.max(np.abs(y)), 1e-20)))
    # Linear upsample via FFT zero-stuffing for a cheap oversampling peak.
    n = len(y)
    spec = np.fft.rfft(y)
    up = np.fft.irfft(spec, n=n * 4)
    return float(20 * np.log10(max(np.max(np.abs(up)), 1e-20)))


def _approx_lufs(y: np.ndarray, sr: int) -> float:
    """Very rough K-weighted loudness proxy (not a BS.1770 meter)."""
    # Pre-filter approximations of the two K-weighting stages.
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [
        1.0,
        -1.69065929318241,
        0.73248077421585,
    ]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    from scipy.signal import lfilter

    z = lfilter(b1, a1, y)
    z = lfilter(b2, a2, z)
    # Gating-free mean square over active region.
    mask = _active_mask(y, sr, 0.1)
    ms = float(np.mean(z[mask] ** 2)) if mask.any() else float(np.mean(z**2))
    return float(-0.691 + 10 * np.log10(max(ms, 1e-20)))


def audio_level_metrics(pairs_manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in pairs_manifest.iterrows():
        yc, sr = m.load(REPO / r.cafe_path if not _P(r.cafe_path).is_absolute() else r.cafe_path)
        ya, _ = m.load(REPO / r.azul_path if not _P(r.azul_path).is_absolute() else r.azul_path)
        yc = yc - np.mean(yc)
        ya = ya - np.mean(ya)
        mc = _active_mask(yc, sr)
        ma = _active_mask(ya, sr)
        rms_c = float(np.sqrt(np.mean(yc[mc] ** 2))) if mc.any() else float(np.sqrt(np.mean(yc**2)))
        rms_a = float(np.sqrt(np.mean(ya[ma] ** 2))) if ma.any() else float(np.sqrt(np.mean(ya**2)))
        peak_c = float(np.max(np.abs(yc)))
        peak_a = float(np.max(np.abs(ya)))
        tp_c = _true_peak_dbfs(yc, sr)
        tp_a = _true_peak_dbfs(ya, sr)
        lufs_c = _approx_lufs(yc, sr)
        lufs_a = _approx_lufs(ya, sr)
        rows.append(
            {
                "pair_id": r.pair_id,
                "rms_active_delta_db": 20 * np.log10(max(rms_a, 1e-20) / max(rms_c, 1e-20)),
                "peak_delta_db": 20 * np.log10(max(peak_a, 1e-20) / max(peak_c, 1e-20)),
                "true_peak_cafe_dbfs": tp_c,
                "true_peak_azul_dbfs": tp_a,
                "true_peak_delta_db": tp_a - tp_c,
                "headroom_cafe_db": -tp_c,
                "headroom_azul_db": -tp_a,
                "crest_cafe_db": tp_c - (20 * np.log10(max(rms_c, 1e-20))),
                "crest_azul_db": tp_a - (20 * np.log10(max(rms_a, 1e-20))),
                "lufs_proxy_cafe": lufs_c,
                "lufs_proxy_azul": lufs_a,
                "lufs_proxy_delta_db": lufs_a - lufs_c,
            }
        )
    return pd.DataFrame(rows)


def deep_gain_catalogue(fund: pd.DataFrame, curve_db: np.ndarray, audio_df: pd.DataFrame) -> dict:
    """Catalogue of gain estimators demanded by §19, side by side."""
    z = v11.gain_observations(curve_db, fund)
    bulk = z[~z.collapsed]
    vals = bulk.g_need.to_numpy(float)
    allv = z.g_need.to_numpy(float)

    per_pair = (
        bulk.groupby("pair")
        .agg(gain_db=("g_need", "mean"), sd=("g_need", "std"), n=("g_need", "size"))
        .reset_index()
    )
    per_pair["weight"] = np.sqrt(per_pair.n) / np.maximum(per_pair.sd.fillna(2.0), 0.5)

    # Bootstrap CI of the pair-balanced mean.
    rng = np.random.default_rng(13013)
    boots = []
    pairs = per_pair.pair.to_numpy()
    for _ in range(400):
        sample = rng.choice(pairs, size=len(pairs), replace=True)
        sub = per_pair.set_index("pair").loc[sample]
        boots.append(float(np.average(sub.gain_db, weights=sub.weight)))
    boots = np.asarray(boots)

    # Trimmed / winsorized / Huber-ish.
    trim = float(stats.trim_mean(vals, 0.1))
    lo, hi = np.percentile(vals, [5, 95])
    wins = float(np.mean(np.clip(vals, lo, hi)))
    # One-step Huber: soft-threshold residuals around the median.
    med = float(np.median(vals))
    mad = float(1.4826 * np.median(np.abs(vals - med))) or 1.0
    u = (vals - med) / (1.5 * mad)
    w = np.where(np.abs(u) <= 1, 1.0, 1.0 / np.abs(u))
    huber = float(np.average(vals, weights=w))

    estimators = {
        "all_mean_db": float(np.mean(allv)),
        "all_median_db": float(np.median(allv)),
        "bulk_mean_db": float(np.mean(vals)),
        "bulk_median_db": float(np.median(vals)),
        "bulk_p25_db": float(np.percentile(vals, 25)),
        "bulk_p75_db": float(np.percentile(vals, 75)),
        "pair_balanced_mean_db": float(np.average(per_pair.gain_db, weights=per_pair.weight)),
        "pair_median_of_medians_db": float(
            bulk.groupby("pair").g_need.median().median()
        ),
        "string_median_of_medians_db": float(
            bulk.groupby("string").g_need.median().median()
        ),
        "trimmed_mean_10_db": trim,
        "winsorized_5_95_mean_db": wins,
        "huber_db": huber,
        "bootstrap_pair_mean_p025_db": float(np.percentile(boots, 2.5)),
        "bootstrap_pair_mean_p975_db": float(np.percentile(boots, 97.5)),
        "collapsed_fraction": float(z.collapsed.mean()),
        "n_bulk": int(len(bulk)),
        "n_all": int(len(z)),
    }

    # Audio-domain estimators (session-matched; instrument difference, not gain knob).
    audio_est = {
        "audio_rms_active_median_db": float(audio_df.rms_active_delta_db.median()),
        "audio_rms_active_mean_db": float(audio_df.rms_active_delta_db.mean()),
        "audio_true_peak_median_db": float(audio_df.true_peak_delta_db.median()),
        "audio_lufs_proxy_median_db": float(audio_df.lufs_proxy_delta_db.median()),
        "audio_peak_median_db": float(audio_df.peak_delta_db.median()),
        "headroom_cafe_min_db": float(audio_df.headroom_cafe_db.min()),
        "headroom_azul_min_db": float(audio_df.headroom_azul_db.min()),
        "headroom_cafe_median_db": float(audio_df.headroom_cafe_db.median()),
        "headroom_azul_median_db": float(audio_df.headroom_azul_db.median()),
        "crest_delta_median_db": float(
            (audio_df.crest_azul_db - audio_df.crest_cafe_db).median()
        ),
    }

    # Energy-neutral from V12 if present.
    summary_v12 = OUT / "RESUMEN_V12.json"
    if summary_v12.exists():
        v12 = json.loads(summary_v12.read_text(encoding="utf-8"))
        estimators["v12_energy_neutral_db"] = float(v12.get("gain_v12_energy_neutral_db", np.nan))
        estimators["v12_loop_db"] = float(v12.get("gain_v12_loop_db", np.nan))
        estimators["v11_db"] = float(v12.get("gain_v11_db", np.nan))

    # Preferred operational gain: pair-balanced bulk mean (consistent with LS).
    estimators["recommended_db"] = estimators["pair_balanced_mean_db"]
    estimators["audio"] = audio_est
    estimators["agreement_note"] = (
        "Audio RMS/true-peak/LUFS measure the instrument level difference under "
        "matched recording conditions; they are not a substitute for the "
        "fundamental residual gain used by the Café→Azul EQ split."
    )
    return estimators


def leave_one_register_out(obs, lams) -> pd.DataFrame:
    frame = pd.DataFrame(obs)
    if "register" not in frame.columns:
        return pd.DataFrame()
    rows = []
    for reg in sorted(frame.register.dropna().unique()):
        train = [o for o in obs if o.get("register") != reg]
        held = [o for o in obs if o.get("register") == reg]
        if not train or not held:
            continue
        beta, _, _ = m.fit_model(train, lams, "JOINT")
        d, X, y, w = m.prepare_obs(held, "JOINT")
        if not len(d):
            continue
        r = y - X @ beta
        rows.append(
            {
                "held_out_register": reg,
                "n_observations": int(len(d)),
                "n_pairs": int(d.pair.nunique()),
                "mae_db": float(np.average(np.abs(r), weights=w)),
                "rmse_db": float(np.sqrt(np.average(r * r, weights=w))),
                "p95_db": float(m.weighted_quantile(np.abs(r), w, 0.95)),
            }
        )
    return pd.DataFrame(rows)


def leave_one_pair_out(obs, lams) -> pd.DataFrame:
    frame = pd.DataFrame(obs)
    rows = []
    for pair in sorted(frame.pair.dropna().unique()):
        train = [o for o in obs if o.get("pair") != pair]
        held = [o for o in obs if o.get("pair") == pair]
        if not train or not held:
            continue
        beta, _, _ = m.fit_model(train, lams, "JOINT")
        d, X, y, w = m.prepare_obs(held, "JOINT")
        if not len(d):
            continue
        r = y - X @ beta
        rows.append(
            {
                "held_out_pair": pair,
                "held_out_family": str(d.family.iloc[0]) if "family" in d.columns else "",
                "n_observations": int(len(d)),
                "mae_db": float(np.average(np.abs(r), weights=w)),
                "rmse_db": float(np.sqrt(np.average(r * r, weights=w))),
                "p95_db": float(m.weighted_quantile(np.abs(r), w, 0.95)),
            }
        )
    return pd.DataFrame(rows)


def leave_one_exercise_out(obs, lams) -> pd.DataFrame:
    """Exercise = family (open / fret12 / chromatic / high / chord)."""
    return v11.leave_one_family_out(obs, lams).rename(
        columns={"held_out_family": "held_out_exercise"}
    )


def main() -> None:
    t0 = time.time()
    run_id = f"v13_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v13", stages=["improve_v13"]
    )

    obs, fund, ton = _load_obs()
    print(f"1 observations={len(obs)} fund={len(fund)} tonal={len(ton)}", flush=True)

    # Prefer V12 energy-neutral gain; fall back to V11 / V10.2.
    gain = None
    if (OUT / "RESUMEN_V12.json").exists():
        gain = float(json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"])
    elif (OUT / "RESUMEN_V11.json").exists():
        gain = float(json.loads((OUT / "RESUMEN_V11.json").read_text())["gain_v11_db"])
    else:
        gain = float(pd.read_csv(OUT / "GAIN_GLOBAL_V10_2.csv").gain_recommended_db[0])
    print(f"2 reference gain for phase demeaning: {gain:+.3f} dB", flush=True)

    print("3 phase curves", flush=True)
    phase = publish_phase_curves(fund, ton, gain)
    att = publish_attack_multiscale()
    print(
        f"   phases finite: "
        + ", ".join(
            f"{ph}={float(np.isfinite(phase[f'{ph}_db']).mean()):.0%}" for ph in PHASES
        ),
        flush=True,
    )
    print(f"   multiscale cells: {len(att)}", flush=True)

    print("4 audio levels / headroom", flush=True)
    pairs_manifest = pd.read_csv(MANIFEST)
    audio_df = audio_level_metrics(pairs_manifest)
    audio_df.to_csv(OUT / "NIVELES_AUDIO_HEADROOM_V13.csv", index=False)
    print(
        audio_df[
            ["pair_id", "rms_active_delta_db", "true_peak_delta_db", "headroom_azul_db"]
        ]
        .round(2)
        .to_string(index=False),
        flush=True,
    )

    # Curve used for residual gain catalogue.
    if (OUT / "CURVAS_DENSAS_V12.csv").exists():
        c12 = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
        curve = np.interp(np.log(m.DENSE_F), np.log(c12.frequency_hz), c12.energy_neutral_db)
    elif (OUT / "CURVAS_DENSAS_V11.csv").exists():
        c11 = pd.read_csv(OUT / "CURVAS_DENSAS_V11.csv")
        curve = np.interp(np.log(m.DENSE_F), np.log(c11.frequency_hz), c11.precise_central_db)
    else:
        c10 = pd.read_csv(OUT / "CURVAS_DENSAS_V10_2.csv")
        curve = np.interp(np.log(m.DENSE_F), np.log(c10.frequency_hz), c10.precise_central_db)

    print("5 deep gain catalogue", flush=True)
    catalogue = deep_gain_catalogue(fund, curve, audio_df)
    (OUT / "GAIN_PROFUNDO_V13.json").write_text(
        json.dumps(catalogue, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Flat CSV of scalar estimators for easy diffing.
    flat = {k: v for k, v in catalogue.items() if not isinstance(v, dict)}
    flat.update({f"audio_{k}": v for k, v in catalogue["audio"].items()})
    pd.DataFrame([flat]).to_csv(OUT / "GAIN_PROFUNDO_V13.csv", index=False)
    print(
        json.dumps(
            {
                "recommended_db": catalogue["recommended_db"],
                "pair_balanced_mean_db": catalogue["pair_balanced_mean_db"],
                "huber_db": catalogue["huber_db"],
                "audio_rms_active_median_db": catalogue["audio"]["audio_rms_active_median_db"],
                "headroom_azul_min_db": catalogue["audio"]["headroom_azul_min_db"],
            },
            indent=2,
        ),
        flush=True,
    )

    lc, _lr, _ = run_config.lambdas()
    if lc is None:
        lc, _lr, _cv, _agg = m.cross_validate(obs)

    print("6 leave-one-register / pair / exercise", flush=True)
    loro = leave_one_register_out(obs, lc)
    loro.to_csv(OUT / "VALIDACION_LORO_V13.csv", index=False)
    print(loro.round(3).to_string(index=False), flush=True)

    lopo = leave_one_pair_out(obs, lc)
    lopo.to_csv(OUT / "VALIDACION_LOPO_V13.csv", index=False)
    print(lopo.round(3).to_string(index=False), flush=True)

    loeo = leave_one_exercise_out(obs, lc)
    loeo.to_csv(OUT / "VALIDACION_LOEO_V13.csv", index=False)
    print(loeo.round(3).to_string(index=False), flush=True)

    summary = {
        "run_id": run_id,
        "reference_gain_db": gain,
        "phase_curves": "CURVAS_POR_FASE_V13.csv",
        "named_curves": [
            "CURVA_ATAQUE_V13.csv",
            "CURVA_SUSTAIN_V13.csv",
            "CURVA_CUERPO_V13.csv",
            "CURVA_ATAQUE_MENOS_CUERPO_V13.csv",
            "CURVA_SUSTAIN_MENOS_CUERPO_V13.csv",
            "CURVA_ATAQUE_MULTIESCALA_V13.csv",
        ],
        "gain_recommended_db": catalogue["recommended_db"],
        "gain_ci95_db": [
            catalogue["bootstrap_pair_mean_p025_db"],
            catalogue["bootstrap_pair_mean_p975_db"],
        ],
        "audio_rms_median_db": catalogue["audio"]["audio_rms_active_median_db"],
        "headroom_azul_min_db": catalogue["audio"]["headroom_azul_min_db"],
        "loro_worst_register": (
            loro.sort_values("rmse_db").iloc[-1].to_dict() if len(loro) else None
        ),
        "lopo_worst_pair": (
            lopo.sort_values("rmse_db").iloc[-1].to_dict() if len(lopo) else None
        ),
        "loeo_worst_exercise": (
            loeo.sort_values("rmse_db").iloc[-1].to_dict() if len(loeo) else None
        ),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V13.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
