"""Discrete anti-error Mooer GE300 fitter for arbitrary target curves."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from paths import discover_repo
from targets import FitTarget


def _load_mooer_model():
    import importlib.util
    import sys

    paths = discover_repo()
    code = paths.mooer_eq / "code"
    sys.path.insert(0, str(code))
    for key in ("mooer_model",):
        if key in sys.modules:
            del sys.modules[key]
    spec = importlib.util.spec_from_file_location("mooer_model", code / "mooer_model.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["mooer_model"] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class FitResult:
    target_name: str
    gains_display_db: list[float]
    frequencies_hz: list[float]
    q_display: float
    global_gain_db: float
    score: float
    metrics: dict
    meta: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _build_bank(mm, freq: np.ndarray):
    model = mm.DEFAULT_MODEL
    gvals = np.arange(model.gain_min_db, model.gain_max_db + 1e-9, model.gain_step_db)
    bank = np.empty((5, len(gvals), len(freq)), dtype=float)
    for i, fc in enumerate(model.frequencies_hz):
        for j, g in enumerate(gvals):
            bank[i, j] = mm.bell_db(freq, fc, g, model)
    return bank, gvals, model


def _response_from_idx(bank, idx, global_gain: float) -> np.ndarray:
    y = np.full(bank.shape[2], global_gain, dtype=float)
    for k in range(5):
        y = y + bank[k, int(idx[k])]
    return y


def _scores_batch(mm, freq, Y, target, unc) -> np.ndarray:
    """Vectorized anti-error scores for many responses Y shape (n, f)."""
    regions = mm.REGIONS
    e = Y - target[None, :]
    rr = []
    for _, lo, hi in regions:
        m = (freq >= lo) & (freq < (hi if hi < 15500 else hi + 1))
        w = 1.0 / (unc[m] ** 2 + 0.12**2)
        w = w / w.sum()
        rr.append(np.sqrt(np.sum(w[None, :] * e[:, m] ** 2, axis=1)))
    rr = np.stack(rr, axis=1)
    worst = rr.max(axis=1)
    avg = rr.mean(axis=1)
    w = 1.0 / (unc**2 + 0.12**2)
    w *= np.where(freq <= 15500, 1.0, np.clip((18000 - freq) / 2500, 0.05, 1.0))
    w = w / w.sum()
    glob = np.sqrt(np.sum(w[None, :] * e * e, axis=1))
    m2540 = (freq >= 25) & (freq <= 40)
    r25 = np.sqrt(np.mean(e[:, m2540] ** 2, axis=1)) if m2540.any() else np.zeros(len(Y))
    i30 = int(np.argmin(np.abs(freq - 30)))
    ae30 = np.abs(e[:, i30])
    p95 = np.percentile(np.abs(e[:, freq <= 15500]), 95, axis=1)
    return worst + 0.35 * avg + 0.10 * glob + 0.025 * p95 + 0.04 * r25 + 0.015 * ae30


def _metrics_one(mm, freq, y, target, unc) -> dict:
    metrics = mm.regional_rmse(freq, y, target, unc)
    e = y - target
    m2540 = (freq >= 25) & (freq <= 40)
    metrics["p95"] = float(np.percentile(np.abs(e[freq <= 15500]), 95))
    metrics["r2540"] = float(np.sqrt(np.mean(e[m2540] ** 2))) if m2540.any() else 0.0
    metrics["ae30"] = float(np.abs(e[np.argmin(np.abs(freq - 30))]))
    metrics["anti_error_score"] = float(
        metrics["worst"]
        + 0.35 * metrics["avg"]
        + 0.10 * metrics["global"]
        + 0.025 * metrics["p95"]
        + 0.04 * metrics["r2540"]
        + 0.015 * metrics["ae30"]
    )
    return metrics


def _gain_to_idx(gvals: np.ndarray, gain_db: float) -> int:
    return int(np.argmin(np.abs(gvals - float(gain_db))))


def _apply_locks(idx: np.ndarray, locked_idx: dict[int, int]) -> np.ndarray:
    out = np.asarray(idx, dtype=int).copy()
    for band, j in locked_idx.items():
        out[int(band)] = int(j)
    return out


def _coordinate_descent(
    bank,
    idx,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    rounds: int = 10,
    locked_bands: set[int] | None = None,
):
    locked_bands = locked_bands or set()
    idx = np.asarray(idx, dtype=int).copy()
    y = _response_from_idx(bank, idx, global_gain)
    best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    for _ in range(rounds):
        improved = False
        for band in range(5):
            if band in locked_bands:
                continue
            base = y - bank[band, idx[band]]
            Y = base[None, :] + bank[band]
            scores = _scores_batch(mm, freq, Y, target, unc)
            jbest = int(np.argmin(scores))
            if scores[jbest] < best_s - 1e-12:
                idx[band] = jbest
                y = Y[jbest]
                best_s = float(scores[jbest])
                improved = True
        if not improved:
            break
    return idx, best_s, y


def _pairwise_polish(
    bank,
    idx,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    locked_bands: set[int] | None = None,
):
    locked_bands = locked_bands or set()
    idx = np.asarray(idx, dtype=int).copy()
    y = _response_from_idx(bank, idx, global_gain)
    best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    n = bank.shape[1]
    free = [i for i in range(5) if i not in locked_bands]
    for ai, a in enumerate(free):
        for b in free[ai + 1 :]:
            base = y - bank[a, idx[a]] - bank[b, idx[b]]
            ias = range(0, n, 2)
            ibs = range(0, n, 2)
            local = (idx[a], idx[b], best_s)
            for ia in ias:
                Y = base[None, :] + bank[a, ia][None, :] + bank[b]
                scores = _scores_batch(mm, freq, Y[list(ibs)], target, unc)
                j = int(np.argmin(scores))
                ib = list(ibs)[j]
                if scores[j] < local[2]:
                    local = (ia, ib, float(scores[j]))
            for ia in range(max(0, local[0] - 1), min(n, local[0] + 2)):
                Y = base[None, :] + bank[a, ia][None, :] + bank[b]
                lo = max(0, local[1] - 1)
                hi = min(n, local[1] + 2)
                scores = _scores_batch(mm, freq, Y[lo:hi], target, unc)
                j = int(np.argmin(scores))
                ib = lo + j
                if scores[j] < local[2]:
                    local = (ia, ib, float(scores[j]))
            idx[a], idx[b] = local[0], local[1]
            y = _response_from_idx(bank, idx, global_gain)
            best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    return idx, best_s, y


def fit_mooer_anti_error(
    target: FitTarget,
    *,
    de_seeds: int = 6,
    random_starts: int = 800,
    seed: int = 20260730,
    locked_gains_db: dict[int, float] | None = None,
) -> FitResult:
    """Fit GE300 discrete gains with anti-error objective.

    ``locked_gains_db`` maps band index → display dB (e.g. ``{4: -16.0}`` locks 18 kHz).
    Frequencies locked 30/148/735/3637/18000, Q display 0.3, global +3 dB.
    """
    mm = _load_mooer_model()
    freq = np.asarray(target.frequency_hz, dtype=float)
    mask = (freq >= 20) & (freq <= 15500)
    f = freq[mask]
    t = np.asarray(target.target_db, dtype=float)[mask]
    u = np.maximum(np.asarray(target.uncertainty_db, dtype=float)[mask], 0.08)

    bank, gvals, model = _build_bank(mm, f)
    rng = np.random.default_rng(seed)

    locked_gains_db = dict(locked_gains_db or {})
    locked_idx = {int(b): _gain_to_idx(gvals, g) for b, g in locked_gains_db.items()}
    locked_bands = set(locked_idx)

    starts = [np.zeros(5, dtype=int)]
    for preset in (
        [15.0, 3.5, -3.5, 16.0, -3.5],
        [-1.5, 3.0, 4.0, 8.5, 1.5],
        [-10.5, 5.5, 2.0, 10.5, 0.0],
        [8.0, 2.0, 0.0, 8.0, 0.0],
        [0.0, 2.0, 0.0, 10.0, 0.0],
        [-8.0, 4.0, 2.0, 10.0, 0.0],
        [16.0, 4.0, -2.0, 16.0, -16.0],
        [0.0, 4.0, 2.0, 12.0, -16.0],
        [-8.0, 6.0, 2.0, 12.0, -16.0],
    ):
        starts.append(np.clip(np.round((np.asarray(preset) + 16) * 2).astype(int), 0, len(gvals) - 1))

    for _ in range(random_starts):
        starts.append(rng.integers(0, len(gvals), size=5))

    starts = [_apply_locks(s, locked_idx) for s in starts]
    free_bands = [i for i in range(5) if i not in locked_bands]

    def continuous_obj(x):
        g = np.zeros(5)
        for band, val in locked_gains_db.items():
            g[int(band)] = float(val)
        for k, band in enumerate(free_bands):
            g[band] = float(x[k])
        y = mm.preset_response_db(f, g, model)
        return float(_scores_batch(mm, f, y[None, :], t, u)[0])

    if free_bands:
        bounds = [(model.gain_min_db, model.gain_max_db)] * len(free_bands)
        for s_i in range(de_seeds):
            res = differential_evolution(
                continuous_obj,
                bounds=bounds,
                seed=seed + s_i,
                popsize=4,
                maxiter=12,
                tol=1e-4,
                polish=True,
            )
            g = np.zeros(5)
            for band, val in locked_gains_db.items():
                g[int(band)] = float(val)
            for k, band in enumerate(free_bands):
                g[band] = float(res.x[k])
            q = np.clip(np.round(g * 2) / 2, model.gain_min_db, model.gain_max_db)
            starts.append(
                _apply_locks(
                    np.clip(np.round((q + 16) * 2).astype(int), 0, len(gvals) - 1),
                    locked_idx,
                )
            )

    candidates = []
    for start in starts:
        start = _apply_locks(start, locked_idx)
        idx, score, y = _coordinate_descent(
            bank, start, f, t, u, mm, model.global_gain_db, locked_bands=locked_bands
        )
        candidates.append((score, idx.copy(), y))

    candidates.sort(key=lambda x: x[0])
    best = None
    for score, idx, y in candidates[:20]:
        idx2, score2, y2 = _pairwise_polish(
            bank, idx, f, t, u, mm, model.global_gain_db, locked_bands=locked_bands
        )
        idx2 = _apply_locks(idx2, locked_idx)
        y2 = _response_from_idx(bank, idx2, model.global_gain_db)
        score2 = float(_scores_batch(mm, f, y2[None, :], t, u)[0])
        if best is None or score2 < best[0]:
            best = (score2, idx2.copy(), y2)

    assert best is not None
    score, idx, y_opt = best
    gains = [float(gvals[i]) for i in idx]
    metrics = _metrics_one(mm, f, y_opt, t, u)

    y_full = mm.preset_response_db(freq, gains, model)
    full_metrics = mm.regional_rmse(freq, y_full, target.target_db, target.uncertainty_db)

    meta = {
        **target.meta,
        "locked_gains_db": {str(k): float(v) for k, v in locked_gains_db.items()},
        "constraints": {
            "frequencies_hz": list(model.frequencies_hz),
            "q_display": model.q_display,
            "global_gain_db": model.global_gain_db,
            "band_18000_locked_db": locked_gains_db.get(4),
        },
    }
    return FitResult(
        target_name=target.name,
        gains_display_db=gains,
        frequencies_hz=list(model.frequencies_hz),
        q_display=model.q_display,
        global_gain_db=model.global_gain_db,
        score=float(score),
        metrics={**metrics, "full_curve": full_metrics},
        meta=meta,
    )


def save_fit(result: FitResult, target: FitTarget, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = result.target_name
    preset_path = out_dir / f"{stem}_mooer_preset.json"
    curve_path = out_dir / f"{stem}_target_vs_mooer.csv"
    metrics_path = out_dir / f"{stem}_metrics.json"

    mm = _load_mooer_model()
    y = mm.preset_response_db(target.frequency_hz, result.gains_display_db, mm.DEFAULT_MODEL)
    pd.DataFrame(
        {
            "frequency_hz": target.frequency_hz,
            "target_db": target.target_db,
            "uncertainty_db": target.uncertainty_db,
            "mooer_db": y,
            "error_db": y - target.target_db,
        }
    ).to_csv(curve_path, index=False)

    payload = {
        **result.to_dict(),
        "order_hz": result.frequencies_hz,
        "pedal": "MOOER GE300",
        "notes": (
            "Gains are GE300 display values at 30/148/735/3637/18000 Hz. "
            "Global locked at +3 dB. Q display locked at 0.3. "
            "Band 18000 Hz may be locked (see meta.locked_gains_db). "
            "Objective = anti-error (worst regional RMSE + balanced penalties)."
        ),
    }
    preset_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    metrics_path.write_text(
        json.dumps(
            {"score": result.score, "metrics": result.metrics, "meta": result.meta},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"preset": preset_path, "curve": curve_path, "metrics": metrics_path}
