"""V11 improvements over the V10.2 Café→Azul estimate.

Runs after `finalize_v10_2_corrected.py` and writes `*_V11.csv` artifacts next to
the V10.2 ones, so both remain comparable. Nothing here overwrites V10.2.

What it fixes, in the order the audit prioritised them:

P0-4  Closes the gain/curve loop. V10.2 fitted Q(f) jointly with an intercept of
      -9.94 dB and then substituted the robust gain of -10.59 dB without
      refitting, leaving ~0.65 dB of level leaking inside the timbre curve.

P0-1b Reports the gain per string and per register. A single scalar hides an
      11.25 dB spread (C_12 -5.40 dB vs B_open -16.65 dB).

P0-5  Publishes an explicit `valid` mask so consumers stop reading regularised
      zeros as measurements, including the AAC codec ceiling.

P0-3  Flags takes whose noise floor makes them unreliable.

P2-4  Adds leave-one-family-out cross-validation, which V10.2 never had.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import OUT, CODE, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(CODE))

import build_v10_2 as m  # noqa: E402
import run_config  # noqa: E402
import run_manifest  # noqa: E402

GAIN_TOL_DB = 0.01
MAX_ITERATIONS = 12

# A distinct sub-population of fundamentals collapses 25-52 dB below the Café
# reference. It is not low-SNR noise (it survives an SNR>=40 dB filter) and its
# match costs are better than average, but it is concentrated in 3 of 14 pairs
# (C_chromatic, B_open, A_open) where notes overlap or the fundamental sits at
# 31-55 Hz. Left in, it skews the distribution to -2.97 and makes the median,
# the mean and the least-squares intercept disagree by up to 2.6 dB. Excluded,
# skew drops to +0.25 and every estimator lands on -11.4 to -11.6 dB.
COLLAPSE_THRESHOLD_DB = -25.0


# ----------------------------------------------------------------- G/Q closure
def fit_with_fixed_gain(obs, lams, gain_db: float, model: str = "JOINT", irls: int = 5):
    """Fit Q(f) and the nuisance offsets with the global gain held fixed.

    The gain becomes a known offset on the fundamental observations instead of a
    free intercept, so level cannot leak into the curve.
    """
    df, X, y, w = m.prepare_obs(obs, model)
    y = y - gain_db * X[:, m.IG]
    X = X.copy()
    X[:, m.IG] = 0.0

    sup = m.node_support(df)
    A, b, pw = m.penalties(*lams, model=model, support=sup)
    pin = np.zeros(m.NP)
    pin[m.IG] = 1.0
    A = np.vstack([A, pin])
    b = np.r_[b, 0.0]
    pw = np.r_[pw, 1e6]

    beta = np.zeros(m.NP)
    rw = np.ones(len(y))
    for _ in range(irls):
        ww = w * rw
        M = X.T @ (ww[:, None] * X) + A.T @ (pw[:, None] * A) + np.eye(m.NP) * 1e-8
        v = X.T @ (ww * y) + A.T @ (pw * b)
        beta = np.linalg.solve(M, v)
        res = y - X @ beta
        sc = m.robust_scale(res)
        u = np.abs(res) / (1.5 * sc)
        rw = np.where(u <= 1, 1.0, 1.0 / u)

    beta = beta.copy()
    beta[m.IG] = gain_db
    return beta, df, sup


def gain_observations(curve_db: np.ndarray, fund: pd.DataFrame) -> pd.DataFrame:
    """Per-observation level requirement `y - Q(f)` on usable fundamentals."""
    qfun = m.curve_fun(curve_db)
    z = fund[
        (fund.snr >= 10) & (fund.match_cost <= 2.8) & fund.phase.isin(["body", "sustain"])
    ].copy()
    z["g_need"] = z.y - z.f.apply(qfun)
    z["collapsed"] = z.g_need < COLLAPSE_THRESHOLD_DB
    return z


def gain_estimators(z: pd.DataFrame) -> dict:
    """Every estimator side by side, with and without the collapse population."""
    from scipy import stats

    def block(v: np.ndarray, tag: str) -> dict:
        return {
            f"{tag}_n": int(len(v)),
            f"{tag}_median_db": float(np.median(v)),
            f"{tag}_mean_db": float(np.mean(v)),
            f"{tag}_skew": float(stats.skew(v)) if len(v) > 2 else float("nan"),
            f"{tag}_sd_db": float(np.std(v)),
        }

    allv = z.g_need.to_numpy(float)
    bulk = z.loc[~z.collapsed, "g_need"].to_numpy(float)
    out = {**block(allv, "all"), **block(bulk, "bulk")}
    out["collapsed_n"] = int(z.collapsed.sum())
    out["collapsed_fraction"] = float(z.collapsed.mean())
    return out


def bulk_gain(curve_db: np.ndarray, fund: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """Gain from the symmetric bulk, balanced per pair.

    Using the bulk mean keeps the estimator consistent with the least-squares
    model: on a symmetric distribution the mean, the median and the weighted
    intercept coincide, so iterating it converges instead of drifting.
    """
    z = gain_observations(curve_db, fund)
    bulk = z[~z.collapsed]
    per_pair = (
        bulk.groupby("pair")
        .agg(
            gain_db=("g_need", "mean"),
            sd=("g_need", "std"),
            n=("g_need", "size"),
        )
        .reset_index()
    )
    per_pair["weight"] = np.sqrt(per_pair.n) / np.maximum(per_pair.sd.fillna(2.0), 0.5)
    # Pair-balanced mean: no single exercise dominates by sheer event count.
    gain = float(np.average(per_pair.gain_db, weights=per_pair.weight))
    return gain, per_pair


def close_gain_curve_loop(obs, lams, fund: pd.DataFrame, gain0: float):
    """Alternate curve fit and gain estimate until the intercept stops moving."""
    history = []
    gain = float(gain0)
    beta = df = None
    per_pair = pd.DataFrame()
    for it in range(1, MAX_ITERATIONS + 1):
        beta, df, _ = fit_with_fixed_gain(obs, lams, gain)
        curve = m.eval_q(beta)
        new_gain, per_pair = bulk_gain(curve, fund)
        delta = new_gain - gain
        history.append(
            {
                "iteration": it,
                "gain_in_db": gain,
                "gain_out_db": new_gain,
                "delta_db": delta,
                "curve_min_db": float(curve.min()),
                "curve_max_db": float(curve.max()),
            }
        )
        gain = new_gain
        if abs(delta) < GAIN_TOL_DB:
            break
    return beta, df, gain, pd.DataFrame(history), per_pair


def fit_report(obs, beta, label: str) -> dict:
    """Weighted fit quality, so a change can be shown to help or hurt."""
    d, X, y, w = m.prepare_obs(obs, "JOINT")
    r = y - X @ beta
    fmask = (d.kind == "fundamental").to_numpy()
    return {
        "variant": label,
        "mae_db": float(np.average(np.abs(r), weights=w)),
        "rmse_db": float(np.sqrt(np.average(r * r, weights=w))),
        "bias_db": float(np.average(r, weights=w)),
        "fund_mae_db": float(np.average(np.abs(r[fmask]), weights=w[fmask])),
        "fund_bias_db": float(np.average(r[fmask], weights=w[fmask])),
    }


# ------------------------------------------------------------ gain structure
def gain_structure(curve_db: np.ndarray, fund: pd.DataFrame) -> pd.DataFrame:
    """Gain broken down by string, register and family instead of one scalar."""
    z = gain_observations(curve_db, fund)
    z = z[~z.collapsed]

    rows = []
    for level, column in (("global", None), ("string", "string"), ("register", "register"), ("family", "family")):
        if column is None:
            groups = [("all", z)]
        elif column not in z.columns:
            continue
        else:
            groups = list(z.groupby(column))
        for name, g in groups:
            if not len(g):
                continue
            vals = g.g_need.to_numpy(float)
            rows.append(
                {
                    "level": level,
                    "group": str(name),
                    "gain_db": float(np.median(vals)),
                    "mad_db": float(1.4826 * np.median(np.abs(vals - np.median(vals)))),
                    "p16_db": float(np.percentile(vals, 16)),
                    "p84_db": float(np.percentile(vals, 84)),
                    "n_observations": int(len(vals)),
                    "n_pairs": int(g.pair.nunique()),
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------------- validity mask
def validity_mask(curve: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Mark where the curve is a measurement and where it is regularisation."""
    v = cfg.get("validity", {})
    lo = float(v.get("shrink_below_hz", 28))
    hi = float(v.get("shrink_above_hz", 12000))
    codec = float(v.get("codec_reliable_max_hz", 15000))

    f = curve.frequency_hz.to_numpy(float)
    pairs = curve.effective_pairs.to_numpy(float)

    reason = np.full(len(f), "measured", dtype=object)
    reason[pairs < 2] = "single_pair_inference"
    reason[pairs < 1] = "no_support"
    reason[f < lo] = "regularized_below_shrink"
    reason[f > hi] = "regularized_above_shrink"
    reason[f > codec] = "codec_limited_aac"

    valid = (
        (pairs >= 2)
        & (f >= lo)
        & (f <= hi)
        & (f <= codec)
    )
    confidence = np.clip(pairs / 4.0, 0.0, 1.0)
    confidence[~valid] = 0.0

    out = curve[["frequency_hz", "effective_pairs"]].copy()
    out["valid"] = valid
    out["reason"] = reason
    out["confidence"] = confidence
    return out


# --------------------------------------------------------------- audio QC
def take_quality(pairs_manifest: pd.DataFrame) -> pd.DataFrame:
    """Per-file noise floor and SNR, so degraded takes can be down-weighted."""
    rows = []
    for _, r in pairs_manifest.iterrows():
        for role, path in (("cafe", r.cafe_path), ("azul", r.azul_path)):
            y, _sr = m.load(path)
            y = y - np.mean(y)
            n = int(0.02 * m.SR)
            fr = y[: len(y) // n * n].reshape(-1, n)
            e = np.sqrt(np.mean(fr**2, axis=1))
            peak_frame = e.max()
            first = int(np.argmax(e > 0.05 * peak_frame)) if np.any(e > 0.05 * peak_frame) else len(e)
            k = max(first - 5, 0)
            pre = fr[:k].ravel()
            floor = float(np.sqrt(np.mean(pre**2))) if len(pre) >= n else float(np.percentile(e, 5))
            act = fr[e > 0.25 * peak_frame]
            sig = float(np.sqrt(np.mean(act**2))) if len(act) else float(np.sqrt(np.mean(y**2)))
            snr = 20 * np.log10(sig / max(floor, 1e-20))
            rows.append(
                {
                    "pair_id": r.pair_id,
                    "role": role,
                    "file": _P(path).name,
                    "leading_silence_s": round(k * 0.02, 2),
                    "floor_dbfs": round(20 * np.log10(max(floor, 1e-20)), 2),
                    "signal_dbfs": round(20 * np.log10(max(sig, 1e-20)), 2),
                    "snr_db": round(snr, 2),
                }
            )
    df = pd.DataFrame(rows)
    df["degraded"] = df.snr_db < 20.0
    return df


# ------------------------------------------------- leave-one-family-out CV
def leave_one_family_out(obs, lams) -> pd.DataFrame:
    """Generalisation across exercise types, which V10.2 never measured."""
    frame = pd.DataFrame(obs)
    if "family" not in frame.columns:
        return pd.DataFrame()
    rows = []
    for family in sorted(frame.family.dropna().unique()):
        train = [o for o in obs if o.get("family") != family]
        held = [o for o in obs if o.get("family") == family]
        if not train or not held:
            continue
        beta, _, _ = m.fit_model(train, lams, "JOINT")
        d, X, y, w = m.prepare_obs(held, "JOINT")
        if not len(d):
            continue
        r = y - X @ beta
        rows.append(
            {
                "held_out_family": family,
                "n_observations": int(len(d)),
                "n_pairs": int(d.pair.nunique()),
                "mae_db": float(np.average(np.abs(r), weights=w)),
                "rmse_db": float(np.sqrt(np.average(r * r, weights=w))),
                "p95_db": float(m.weighted_quantile(np.abs(r), w, 0.95)),
            }
        )
    return pd.DataFrame(rows)


def leave_one_string_out(obs, lams) -> pd.DataFrame:
    frame = pd.DataFrame(obs)
    if "string" not in frame.columns:
        return pd.DataFrame()
    rows = []
    for string in sorted(frame.string.dropna().unique()):
        train = [o for o in obs if o.get("string") != string]
        held = [o for o in obs if o.get("string") == string]
        if not train or not held:
            continue
        beta, _, _ = m.fit_model(train, lams, "JOINT")
        d, X, y, w = m.prepare_obs(held, "JOINT")
        if not len(d):
            continue
        r = y - X @ beta
        rows.append(
            {
                "held_out_string": string,
                "n_observations": int(len(d)),
                "mae_db": float(np.average(np.abs(r), weights=w)),
                "rmse_db": float(np.sqrt(np.average(r * r, weights=w))),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- main
def main() -> None:
    t0 = time.time()
    cfg = run_config.load_config()
    run_id = f"v11_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v11", stages=["improve_v11"]
    )

    fund = pd.read_csv(OUT / "FUNDAMENTALES_CORREGIDAS_V10_2.csv")
    ton = pd.read_csv(OUT / "TONAL_HARMONICS_CORRECTED_V10_2.csv")
    res = pd.read_csv(OUT / "TRAYECTORIAS_ARMONICAS_V10_2.csv")
    res = res[res.kind == "band_residual"].copy()
    res["weight_base"] *= 0.35
    obs = fund.to_dict("records") + ton.to_dict("records") + res.to_dict("records")
    print(f"1 observations fund={len(fund)} tonal={len(ton)} residual={len(res)}", flush=True)

    lc, lr, _cands = run_config.lambdas()
    if lc is None:
        lc, lr, _cv, _agg = m.cross_validate(obs)
    print(f"2 lambda central={lc} robust={lr}", flush=True)

    v10 = pd.read_csv(OUT / "CURVAS_DENSAS_V10_2.csv")
    gain_v10 = float(pd.read_csv(OUT / "GAIN_GLOBAL_V10_2.csv").gain_recommended_db[0])

    print("3 closing gain/curve loop", flush=True)
    beta, dfn, gain, history, per_pair = close_gain_curve_loop(obs, lc, fund, gain_v10)
    print(history.to_string(index=False), flush=True)
    history.to_csv(OUT / "CONVERGENCIA_GAIN_CURVA_V11.csv", index=False)
    per_pair.to_csv(OUT / "GAIN_POR_PAREJA_V11.csv", index=False)

    # Does closing the loop help or hurt? Compare against V10.2 on the same data.
    beta_free, _, _ = m.fit_model(obs, lc, "JOINT")
    beta_sub = beta_free.copy()
    beta_sub[m.IG] = gain_v10
    fits = pd.DataFrame(
        [
            fit_report(obs, beta_free, "V10_2_free_intercept"),
            fit_report(obs, beta_sub, "V10_2_published_substituted"),
            fit_report(obs, beta, "V11_closed_loop"),
        ]
    )
    fits.to_csv(OUT / "CALIDAD_AJUSTE_V10_2_VS_V11.csv", index=False)
    print(fits.round(4).to_string(index=False), flush=True)

    est = gain_estimators(gain_observations(m.eval_q(beta), fund))
    (OUT / "GAIN_ESTIMADORES_V11.json").write_text(
        json.dumps(est, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(est, indent=2), flush=True)

    beta_r, _, _ = fit_with_fixed_gain(obs, lr, gain)
    boot, _bg, _bo = m.bootstrap(obs, lc, 120)
    central, robust, safe, param, no_sub, no_high, lo, hi, supp, cut, centers, Qs, gains = (
        m.make_variants(beta, beta_r, boot, dfn)
    )

    support = m.support_dense(dfn)
    curve = pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "precise_central_db": central,
            "precise_robust_db": robust,
            "safe_db": safe,
            "parametric_db": param,
            "no_sub_db": no_sub,
            "no_high_db": no_high,
            "ci95_low_db": lo,
            "ci95_high_db": hi,
            "effective_pairs": [x[0] for x in support],
            "strings": [x[1] for x in support],
            "families": [x[2] for x in support],
            "median_snr_db": [x[3] for x in support],
            "max_pair_influence": [x[4] for x in support],
            "support_state": [x[5] for x in support],
        }
    )
    mask = validity_mask(curve, cfg)
    curve = curve.merge(mask[["frequency_hz", "valid", "reason", "confidence"]], on="frequency_hz")
    curve["total_central_with_gain_db"] = curve.precise_central_db + gain
    curve["pipeline_version"] = "V11.0"
    curve.to_csv(OUT / "CURVAS_DENSAS_V11.csv", index=False)
    mask.to_csv(OUT / "MASCARA_VALIDEZ_V11.csv", index=False)

    print("4 gain structure", flush=True)
    structure = gain_structure(central, fund)
    structure.to_csv(OUT / "GAIN_ESTRUCTURA_V11.csv", index=False)
    print(structure.to_string(index=False), flush=True)

    print("5 take quality", flush=True)
    pairs_manifest = pd.read_csv(run_manifest.MANIFEST)
    qc = take_quality(pairs_manifest)
    qc.to_csv(OUT / "CALIDAD_TOMAS_V11.csv", index=False)
    print(f"   tomas degradadas: {int(qc.degraded.sum())}/{len(qc)}", flush=True)

    print("6 leave-one-family-out / leave-one-string-out", flush=True)
    lofo = leave_one_family_out(obs, lc)
    lofo.to_csv(OUT / "VALIDACION_LOFO_V11.csv", index=False)
    print(lofo.to_string(index=False), flush=True)
    loso = leave_one_string_out(obs, lc)
    loso.to_csv(OUT / "VALIDACION_LOSO_V11.csv", index=False)

    # V10.2 vs V11 comparison, restricted to where the curve is a measurement.
    f = m.DENSE_F
    c10 = np.interp(np.log(f), np.log(v10.frequency_hz), v10.precise_central_db)
    delta = central - c10
    valid = curve.valid.to_numpy(bool)
    regions = [(20, 60, "20-60"), (60, 250, "60-250"), (250, 1000, "250-1k"),
               (1000, 2000, "1k-2k"), (2000, 4000, "2k-4k"), (4000, 8000, "4k-8k"),
               (8000, 20000, "8k-20k")]
    rows = []
    for a, b, name in regions:
        sel = (f >= a) & (f < b)
        sel_v = sel & valid
        rows.append(
            {
                "region": name,
                "rmse_db": float(np.sqrt(np.mean(delta[sel] ** 2))),
                "max_abs_db": float(np.abs(delta[sel]).max()),
                "mean_db": float(np.mean(delta[sel])),
                "rmse_valid_db": float(np.sqrt(np.mean(delta[sel_v] ** 2))) if sel_v.any() else np.nan,
                "valid_fraction": float(sel_v.sum() / max(sel.sum(), 1)),
            }
        )
    comparison = pd.DataFrame(rows)
    comparison.to_csv(OUT / "COMPARACION_V10_2_VS_V11.csv", index=False)
    print(comparison.round(3).to_string(index=False), flush=True)

    summary = {
        "run_id": run_id,
        "gain_v10_2_db": gain_v10,
        "gain_v11_db": gain,
        "gain_shift_db": gain - gain_v10,
        "loop_iterations": int(len(history)),
        "loop_converged": bool(abs(history.delta_db.iloc[-1]) < GAIN_TOL_DB),
        "final_intercept_residual_db": float(history.delta_db.iloc[-1]),
        "curve_min_db": float(central.min()),
        "curve_max_db": float(central.max()),
        "valid_fraction": float(curve.valid.mean()),
        "degraded_takes": int(qc.degraded.sum()),
        "gain_spread_by_string_db": float(
            structure[structure.level == "string"].gain_db.max()
            - structure[structure.level == "string"].gain_db.min()
        )
        if (structure.level == "string").any()
        else None,
        "lofo_worst_family": lofo.sort_values("rmse_db").iloc[-1].to_dict() if len(lofo) else None,
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V11.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
