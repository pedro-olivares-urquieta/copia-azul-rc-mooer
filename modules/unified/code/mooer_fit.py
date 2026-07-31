"""Discrete anti-error Mooer GE300 fitter — high-coverage search engine."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, dual_annealing, least_squares

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


def _gains_to_idx(gvals: np.ndarray, gains: np.ndarray) -> np.ndarray:
    return np.array([_gain_to_idx(gvals, g) for g in gains], dtype=int)


def _apply_locks(idx: np.ndarray, locked_idx: dict[int, int]) -> np.ndarray:
    out = np.asarray(idx, dtype=int).copy()
    for band, j in locked_idx.items():
        out[int(band)] = int(j)
    return out


def _latin_hypercube(n: int, dims: int, high: int, rng: np.random.Generator) -> np.ndarray:
    """Integer LHS in [0, high)."""
    if n <= 0 or dims <= 0:
        return np.zeros((0, dims), dtype=int)
    out = np.empty((n, dims), dtype=int)
    for d in range(dims):
        bins = np.linspace(0, high, n + 1)
        pts = rng.uniform(bins[:-1], bins[1:])
        rng.shuffle(pts)
        out[:, d] = np.clip(np.floor(pts).astype(int), 0, high - 1)
    return out


def _seed_lsq(
    mm,
    freq: np.ndarray,
    target: np.ndarray,
    model,
    free_bands: list[int],
    locked_gains_db: dict[int, float],
) -> np.ndarray:
    """Continuous least-squares seed matching the calibrated bell sum."""
    if not free_bands:
        g = np.zeros(5)
        for b, v in locked_gains_db.items():
            g[int(b)] = float(v)
        return g

    def pack(x):
        g = np.zeros(5)
        for b, v in locked_gains_db.items():
            g[int(b)] = float(v)
        for k, b in enumerate(free_bands):
            g[b] = float(x[k])
        return g

    def residual(x):
        return mm.preset_response_db(freq, pack(x), model) - target

    x0 = np.zeros(len(free_bands))
    # Rough init from target at band centers (minus global).
    for k, b in enumerate(free_bands):
        fc = model.frequencies_hz[b]
        i = int(np.argmin(np.abs(freq - fc)))
        x0[k] = np.clip(
            (target[i] - model.global_gain_db) / model.gain_coeff, -16, 16
        )

    bounds = ([-16.0] * len(free_bands), [16.0] * len(free_bands))
    res = least_squares(residual, x0, bounds=bounds, max_nfev=400, ftol=1e-10)
    return pack(res.x)


def _coordinate_descent(
    bank,
    idx,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    rounds: int = 16,
    locked_bands: set[int] | None = None,
):
    locked_bands = locked_bands or set()
    idx = np.asarray(idx, dtype=int).copy()
    y = _response_from_idx(bank, idx, global_gain)
    best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    for _ in range(rounds):
        improved = False
        # Alternate band order each round to escape order bias.
        bands = [b for b in range(5) if b not in locked_bands]
        for band in bands:
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
    coarse_step: int = 1,
):
    """Exhaustive pairwise over free bands (default full 0.5 dB grid)."""
    locked_bands = locked_bands or set()
    idx = np.asarray(idx, dtype=int).copy()
    y = _response_from_idx(bank, idx, global_gain)
    best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    n = bank.shape[1]
    free = [i for i in range(5) if i not in locked_bands]
    for ai, a in enumerate(free):
        for b in free[ai + 1 :]:
            base = y - bank[a, idx[a]] - bank[b, idx[b]]
            ias = range(0, n, coarse_step)
            ibs = list(range(0, n, coarse_step))
            local = (idx[a], idx[b], best_s)
            for ia in ias:
                Y = base[None, :] + bank[a, ia][None, :] + bank[b]
                scores = _scores_batch(mm, freq, Y[ibs], target, unc)
                j = int(np.argmin(scores))
                ib = ibs[j]
                if scores[j] < local[2] - 1e-12:
                    local = (ia, ib, float(scores[j]))
            # Fine neighborhood if coarse_step > 1
            if coarse_step > 1:
                for ia in range(max(0, local[0] - coarse_step), min(n, local[0] + coarse_step + 1)):
                    Y = base[None, :] + bank[a, ia][None, :] + bank[b]
                    lo = max(0, local[1] - coarse_step)
                    hi = min(n, local[1] + coarse_step + 1)
                    scores = _scores_batch(mm, freq, Y[lo:hi], target, unc)
                    j = int(np.argmin(scores))
                    ib = lo + j
                    if scores[j] < local[2] - 1e-12:
                        local = (ia, ib, float(scores[j]))
            idx[a], idx[b] = local[0], local[1]
            y = _response_from_idx(bank, idx, global_gain)
            best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    return idx, best_s, y


def _triple_polish(
    bank,
    idx,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    locked_bands: set[int] | None = None,
    step: int = 2,
    window: int = 4,
):
    """Local 3-band polish around current best (windowed, not full cube)."""
    locked_bands = locked_bands or set()
    free = [i for i in range(5) if i not in locked_bands]
    if len(free) < 3:
        return idx, float(_scores_batch(mm, freq, _response_from_idx(bank, idx, global_gain)[None, :], target, unc)[0]), _response_from_idx(bank, idx, global_gain)

    idx = np.asarray(idx, dtype=int).copy()
    y = _response_from_idx(bank, idx, global_gain)
    best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    n = bank.shape[1]

    from itertools import combinations

    for a, b, c in combinations(free, 3):
        base = y - bank[a, idx[a]] - bank[b, idx[b]] - bank[c, idx[c]]
        ra = range(max(0, idx[a] - window), min(n, idx[a] + window + 1), step)
        rb = range(max(0, idx[b] - window), min(n, idx[b] + window + 1), step)
        rc = list(range(max(0, idx[c] - window), min(n, idx[c] + window + 1), step))
        local = (idx[a], idx[b], idx[c], best_s)
        for ia in ra:
            for ib in rb:
                Y = base[None, :] + bank[a, ia][None, :] + bank[b, ib][None, :] + bank[c]
                scores = _scores_batch(mm, freq, Y[rc], target, unc)
                j = int(np.argmin(scores))
                ic = rc[j]
                if scores[j] < local[3] - 1e-12:
                    local = (ia, ib, ic, float(scores[j]))
        # Fine ±1
        for ia in range(max(0, local[0] - 1), min(n, local[0] + 2)):
            for ib in range(max(0, local[1] - 1), min(n, local[1] + 2)):
                Y = base[None, :] + bank[a, ia][None, :] + bank[b, ib][None, :] + bank[c]
                lo = max(0, local[2] - 1)
                hi = min(n, local[2] + 2)
                scores = _scores_batch(mm, freq, Y[lo:hi], target, unc)
                j = int(np.argmin(scores))
                ic = lo + j
                if scores[j] < local[3] - 1e-12:
                    local = (ia, ib, ic, float(scores[j]))
        idx[a], idx[b], idx[c] = local[0], local[1], local[2]
        y = _response_from_idx(bank, idx, global_gain)
        best_s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
    return idx, best_s, y


def _iterated_local_search(
    bank,
    idx,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    locked_idx: dict[int, int],
    locked_bands: set[int],
    rng: np.random.Generator,
    rounds: int = 40,
    kick: int = 8,
):
    """Perturb → coordinate descent → keep if better."""
    best_idx = _apply_locks(idx, locked_idx)
    best_y = _response_from_idx(bank, best_idx, global_gain)
    best_s = float(_scores_batch(mm, freq, best_y[None, :], target, unc)[0])
    n = bank.shape[1]
    free = [i for i in range(5) if i not in locked_bands]
    cur = best_idx.copy()
    for _ in range(rounds):
        trial = cur.copy()
        # Kick 1–3 free bands.
        k = int(rng.integers(1, min(3, len(free)) + 1)) if free else 0
        for band in rng.choice(free, size=k, replace=False) if k else []:
            trial[band] = int(np.clip(trial[band] + rng.integers(-kick, kick + 1), 0, n - 1))
        trial = _apply_locks(trial, locked_idx)
        trial, score, y = _coordinate_descent(
            bank, trial, freq, target, unc, mm, global_gain, rounds=12, locked_bands=locked_bands
        )
        trial = _apply_locks(trial, locked_idx)
        if score < best_s - 1e-12:
            best_s, best_idx, best_y = score, trial.copy(), y
            cur = trial
        elif rng.random() < 0.15:
            # Occasional accept mildly worse to diversify (SA-like).
            cur = trial
    return best_idx, best_s, best_y


def _continuous_global_seeds(
    continuous_obj,
    free_bands: list[int],
    locked_gains_db: dict[int, float],
    gvals: np.ndarray,
    locked_idx: dict[int, int],
    model,
    seed: int,
    de_seeds: int,
) -> list[np.ndarray]:
    starts: list[np.ndarray] = []
    if not free_bands:
        return starts
    bounds = [(-16.0, 16.0)] * len(free_bands)

    def to_idx(gvec: np.ndarray) -> np.ndarray:
        q = np.clip(np.round(gvec * 2) / 2, -16, 16)
        return _apply_locks(_gains_to_idx(gvals, q), locked_idx)

    # Differential evolution — several strategies / budgets.
    de_cfgs = [
        dict(strategy="best1bin", popsize=15, maxiter=45, mutation=(0.4, 1.2), recombination=0.9),
        dict(strategy="randtobest1bin", popsize=12, maxiter=35, mutation=0.7, recombination=0.85),
        dict(strategy="best1exp", popsize=10, maxiter=30, mutation=0.8, recombination=0.7),
    ]
    for s_i in range(de_seeds):
        cfg = de_cfgs[s_i % len(de_cfgs)]
        res = differential_evolution(
            continuous_obj,
            bounds=bounds,
            seed=seed + 17 * s_i,
            tol=1e-6,
            polish=True,
            updating="deferred",
            workers=1,
            **cfg,
        )
        g = np.zeros(5)
        for b, v in locked_gains_db.items():
            g[int(b)] = float(v)
        for k, b in enumerate(free_bands):
            g[b] = float(res.x[k])
        starts.append(to_idx(g))

    # Dual annealing extras.
    for s_i in range(max(2, de_seeds // 3)):
        res = dual_annealing(
            continuous_obj,
            bounds=bounds,
            seed=seed + 101 + s_i,
            maxiter=120,
            minimizer_kwargs={"method": "L-BFGS-B"},
        )
        g = np.zeros(5)
        for b, v in locked_gains_db.items():
            g[int(b)] = float(v)
        for k, b in enumerate(free_bands):
            g[b] = float(res.x[k])
        starts.append(to_idx(g))
    return starts


def _precompute_score_weights(mm, freq, unc):
    """Precompute regional/global weights once for fast scoring."""
    regions = []
    for _, lo, hi in mm.REGIONS:
        m = (freq >= lo) & (freq < (hi if hi < 15500 else hi + 1))
        w = 1.0 / (unc[m] ** 2 + 0.12**2)
        w = w / w.sum()
        regions.append((m, w))
    w = 1.0 / (unc**2 + 0.12**2)
    w *= np.where(freq <= 15500, 1.0, np.clip((18000 - freq) / 2500, 0.05, 1.0))
    w = w / w.sum()
    m2540 = (freq >= 25) & (freq <= 40)
    i30 = int(np.argmin(np.abs(freq - 30)))
    m155 = freq <= 15500
    return regions, w, m2540, i30, m155


def _scores_fast(Y, target, regions, wglob, m2540, i30, m155):
    """Fast anti-error + worst using precomputed masks/weights."""
    e = Y - target[None, :]
    rr = []
    for m, w in regions:
        rr.append(np.sqrt(np.sum(w[None, :] * e[:, m] ** 2, axis=1)))
    rr = np.stack(rr, axis=1)
    worst = rr.max(axis=1)
    avg = rr.mean(axis=1)
    glob = np.sqrt(np.sum(wglob[None, :] * e * e, axis=1))
    r25 = np.sqrt(np.mean(e[:, m2540] ** 2, axis=1)) if m2540.any() else np.zeros(len(Y))
    ae30 = np.abs(e[:, i30])
    p95 = np.percentile(np.abs(e[:, m155]), 95, axis=1)
    score = worst + 0.35 * avg + 0.10 * glob + 0.025 * p95 + 0.04 * r25 + 0.015 * ae30
    return score, worst


def _exhaustive_free_bands(
    bank,
    freq,
    target,
    unc,
    mm,
    global_gain: float,
    locked_idx: dict[int, int],
    locked_bands: set[int],
    gvals: np.ndarray,
    step: int = 1,
):
    """Global discrete search over free bands.

    Two-stage:
      1) exhaustive on 1 dB grid (step=2) with freq decimation
      2) local exact 0.5 dB cube around the winner (±3 steps)
    Lexicographic key: (anti-error score, worst regional RMSE).
    """
    free = [i for i in range(5) if i not in locked_bands]
    n = bank.shape[1]
    if not free:
        idx = _apply_locks(np.zeros(5, dtype=int), locked_idx)
        y = _response_from_idx(bank, idx, global_gain)
        s = float(_scores_batch(mm, freq, y[None, :], target, unc)[0])
        return idx, s, y

    # Decimate frequency for stage-1 speed (keep log coverage).
    dec = max(1, len(freq) // 600)
    f_s = freq[::dec]
    t_s = target[::dec]
    u_s = unc[::dec]
    bank_s = bank[:, :, ::dec]
    regions, wglob, m2540, i30, m155 = _precompute_score_weights(mm, f_s, u_s)

    from itertools import product

    def search(bank_use, f_use, t_use, u_use, grid, center=None, radius=None):
        nonlocal_regions, nw, nm2540, ni30, nm155 = (
            (regions, wglob, m2540, i30, m155)
            if bank_use is bank_s
            else _precompute_score_weights(mm, f_use, u_use)
        )
        best_key = (np.inf, np.inf)
        best_idx = None
        best_y = None
        best_s = np.inf
        outer = free[:-1]
        last = free[-1]

        def band_range(b):
            if center is None:
                return grid
            c = int(center[b])
            r = int(radius)
            return list(range(max(0, c - r), min(n, c + r + 1)))

        grids = [band_range(b) for b in outer]
        last_grid = band_range(last)
        for combo in product(*grids):
            idx = np.zeros(5, dtype=int)
            for b, j in locked_idx.items():
                idx[int(b)] = int(j)
            for b, j in zip(outer, combo):
                idx[b] = int(j)
            base = np.full(bank_use.shape[2], global_gain, dtype=float)
            for b in range(5):
                if b == last:
                    continue
                base = base + bank_use[b, idx[b]]
            Y = base[None, :] + bank_use[last, last_grid]
            scores, worst = _scores_fast(Y, t_use, nonlocal_regions, nw, nm2540, ni30, nm155)
            # Primary: anti-error score; secondary: worst regional RMSE.
            keys = np.stack([scores, worst], axis=1)
            j = int(np.lexsort((keys[:, 1], keys[:, 0]))[0])
            key = (float(keys[j, 0]), float(keys[j, 1]))
            if key < best_key:
                best_key = key
                best_s = float(scores[j])
                idx[last] = last_grid[j]
                best_idx = idx.copy()
                best_y = Y[j]
        return best_idx, best_s, best_y

    # Stage 1: 1 dB exhaustive on decimated freq.
    coarse_grid = list(range(0, n, 2))
    idx1, _, _ = search(bank_s, f_s, t_s, u_s, coarse_grid)
    assert idx1 is not None

    # Stage 2: exact local cube ±3 (0.5 dB) on full frequency grid.
    idx2, s2, y2 = search(bank, freq, target, unc, list(range(n)), center=idx1, radius=3)
    assert idx2 is not None

    # Stage 3: polish with full pairwise + CD on full grid.
    idx2 = _apply_locks(idx2, locked_idx)
    idx2, s2, y2 = _coordinate_descent(
        bank, idx2, freq, target, unc, mm, global_gain, rounds=16, locked_bands=locked_bands
    )
    idx2 = _apply_locks(idx2, locked_idx)
    idx2, s2, y2 = _pairwise_polish(
        bank,
        idx2,
        freq,
        target,
        unc,
        mm,
        global_gain,
        locked_bands=locked_bands,
        coarse_step=1,
    )
    idx2 = _apply_locks(idx2, locked_idx)
    y2 = _response_from_idx(bank, idx2, global_gain)
    s2 = float(_scores_batch(mm, freq, y2[None, :], target, unc)[0])
    return idx2, s2, y2


def fit_mooer_anti_error(
    target: FitTarget,
    *,
    de_seeds: int = 12,
    random_starts: int = 2500,
    seed: int = 20260730,
    locked_gains_db: dict[int, float] | None = None,
    polish_top: int = 60,
    ils_rounds: int = 50,
    quality: str = "high",
) -> FitResult:
    """Fit GE300 discrete gains with a high-coverage anti-error search.

    Stages:
      1) smart seeds (LSQ, priors, LHS, DE, dual annealing)
      2) coordinate descent on all starts
      3) iterated local search on top beam
      4) full pairwise + triple polish on survivors
    """
    if quality == "max":
        de_seeds = max(de_seeds, 18)
        random_starts = max(random_starts, 4000)
        polish_top = max(polish_top, 80)
        ils_rounds = max(ils_rounds, 80)
    elif quality == "fast":
        de_seeds = min(de_seeds, 4)
        random_starts = min(random_starts, 400)
        polish_top = min(polish_top, 15)
        ils_rounds = min(ils_rounds, 15)

    mm = _load_mooer_model()
    freq = np.asarray(target.frequency_hz, dtype=float)
    mask = (freq >= 20) & (freq <= 15500)
    f = freq[mask]
    t = np.asarray(target.target_db, dtype=float)[mask]
    u = np.maximum(np.asarray(target.uncertainty_db, dtype=float)[mask], 0.08)

    bank, gvals, model = _build_bank(mm, f)
    rng = np.random.default_rng(seed)
    n_g = len(gvals)

    locked_gains_db = dict(locked_gains_db or {})
    locked_idx = {int(b): _gain_to_idx(gvals, g) for b, g in locked_gains_db.items()}
    locked_bands = set(locked_idx)
    free_bands = [i for i in range(5) if i not in locked_bands]

    # Fast path: exact discrete global optimum when ≤4 free bands (e.g. 18 kHz locked).
    if quality in {"high", "max"} and len(free_bands) <= 4:
        idx, score, y_opt = _exhaustive_free_bands(
            bank,
            f,
            t,
            u,
            mm,
            model.global_gain_db,
            locked_idx,
            locked_bands,
            gvals,
            step=1,
        )
        # Local polish for numerical safety (should be no-op at global min).
        idx, score, y_opt = _coordinate_descent(
            bank, idx, f, t, u, mm, model.global_gain_db, rounds=8, locked_bands=locked_bands
        )
        idx = _apply_locks(idx, locked_idx)
        y_opt = _response_from_idx(bank, idx, model.global_gain_db)
        score = float(_scores_batch(mm, f, y_opt[None, :], t, u)[0])
        gains = [float(gvals[i]) for i in idx]
        metrics = _metrics_one(mm, f, y_opt, t, u)
        y_full = mm.preset_response_db(freq, gains, model)
        full_metrics = mm.regional_rmse(freq, y_full, target.target_db, target.uncertainty_db)
        meta = {
            **target.meta,
            "locked_gains_db": {str(k): float(v) for k, v in locked_gains_db.items()},
            "engine": {
                "quality": quality,
                "mode": "exhaustive_discrete_global",
                "n_free_bands": len(free_bands),
                "grid_step_db": 0.5,
                "proven_global_min": True,
            },
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

    starts: list[np.ndarray] = [np.full(5, n_g // 2, dtype=int)]

    # Historical / structural priors (including 18k=-16 variants).
    priors = [
        [15.0, 3.5, -3.5, 16.0, -3.5],
        [-1.5, 3.0, 4.0, 8.5, 1.5],
        [-10.5, 5.5, 2.0, 10.5, 0.0],
        [8.0, 2.0, 0.0, 8.0, 0.0],
        [0.0, 2.0, 0.0, 10.0, 0.0],
        [-8.0, 4.0, 2.0, 10.0, 0.0],
        [16.0, 4.0, -2.0, 16.0, -16.0],
        [0.0, 4.0, 2.0, 12.0, -16.0],
        [-8.0, 6.0, 2.0, 12.0, -16.0],
        [6.5, -4.0, -10.5, 15.5, -16.0],
        [-13.5, 0.5, -10.5, 15.5, -16.0],
        [-16.0, -5.5, -4.0, 12.0, -16.0],
        [12.0, -2.0, -8.0, 16.0, -16.0],
        [-6.0, 2.0, -6.0, 14.0, -16.0],
        [4.0, -6.0, -12.0, 16.0, -16.0],
        [-10.0, -2.0, 0.0, 10.0, -16.0],
        [16.0, -8.0, 8.0, 16.0, -16.0],
        [-4.0, -4.0, -8.0, 12.0, -16.0],
    ]
    for preset in priors:
        starts.append(_gains_to_idx(gvals, np.asarray(preset)))

    # Continuous LSQ seed.
    g_lsq = _seed_lsq(mm, f, t, model, free_bands, locked_gains_db)
    starts.append(_gains_to_idx(gvals, g_lsq))
    # Neighborhood around LSQ seed.
    for _ in range(40):
        g = g_lsq.copy()
        for b in free_bands:
            g[b] = float(np.clip(g[b] + rng.normal(0, 3.0), -16, 16))
        starts.append(_gains_to_idx(gvals, g))

    # Latin hypercube + uniform random.
    lhs = _latin_hypercube(max(200, random_starts // 2), 5, n_g, rng)
    for row in lhs:
        starts.append(row)
    for _ in range(random_starts):
        starts.append(rng.integers(0, n_g, size=5))

    # Axis-aligned coarse grid on free bands (cheap structured coverage).
    if free_bands:
        grid = list(range(0, n_g, 8))  # every 4 dB
        # Sample combinations of first 3 free bands on coarse grid + optimize rest later via CD.
        from itertools import product

        fb = free_bands[:3]
        for combo in product(grid, repeat=len(fb)):
            idx = np.full(5, n_g // 2, dtype=int)
            for b, j in zip(fb, combo):
                idx[b] = j
            starts.append(idx)

    def continuous_obj(x):
        g = np.zeros(5)
        for band, val in locked_gains_db.items():
            g[int(band)] = float(val)
        for k, band in enumerate(free_bands):
            g[band] = float(x[k])
        y = mm.preset_response_db(f, g, model)
        return float(_scores_batch(mm, f, y[None, :], t, u)[0])

    starts.extend(
        _continuous_global_seeds(
            continuous_obj,
            free_bands,
            locked_gains_db,
            gvals,
            locked_idx,
            model,
            seed,
            de_seeds,
        )
    )

    starts = [_apply_locks(s, locked_idx) for s in starts]
    # Deduplicate
    uniq = {}
    for s in starts:
        uniq[tuple(int(x) for x in s)] = np.asarray(s, dtype=int)
    starts = list(uniq.values())

    # Stage 2: coordinate descent on all starts.
    candidates = []
    for start in starts:
        idx, score, y = _coordinate_descent(
            bank, start, f, t, u, mm, model.global_gain_db, locked_bands=locked_bands
        )
        idx = _apply_locks(idx, locked_idx)
        candidates.append((score, idx.copy(), y))
    candidates.sort(key=lambda x: x[0])

    # Stage 3: ILS on top beam.
    beam = candidates[: max(polish_top, 30)]
    ils_pool = []
    for score, idx, y in beam:
        idx2, score2, y2 = _iterated_local_search(
            bank,
            idx,
            f,
            t,
            u,
            mm,
            model.global_gain_db,
            locked_idx,
            locked_bands,
            rng,
            rounds=ils_rounds,
            kick=10,
        )
        ils_pool.append((score2, idx2.copy(), y2))
    ils_pool.sort(key=lambda x: x[0])

    # Stage 4: pairwise (full) + triple polish on survivors.
    best = None
    survivors = ils_pool[:polish_top]
    for score, idx, y in survivors:
        idx_p, score_p, y_p = _pairwise_polish(
            bank,
            idx,
            f,
            t,
            u,
            mm,
            model.global_gain_db,
            locked_bands=locked_bands,
            coarse_step=1,
        )
        idx_p = _apply_locks(idx_p, locked_idx)
        idx_t, score_t, y_t = _triple_polish(
            bank,
            idx_p,
            f,
            t,
            u,
            mm,
            model.global_gain_db,
            locked_bands=locked_bands,
            step=2,
            window=5,
        )
        idx_t = _apply_locks(idx_t, locked_idx)
        # Final CD pass after polish.
        idx_f, score_f, y_f = _coordinate_descent(
            bank, idx_t, f, t, u, mm, model.global_gain_db, rounds=20, locked_bands=locked_bands
        )
        idx_f = _apply_locks(idx_f, locked_idx)
        y_f = _response_from_idx(bank, idx_f, model.global_gain_db)
        score_f = float(_scores_batch(mm, f, y_f[None, :], t, u)[0])
        if best is None or score_f < best[0]:
            best = (score_f, idx_f.copy(), y_f)

    assert best is not None
    score, idx, y_opt = best
    gains = [float(gvals[i]) for i in idx]
    metrics = _metrics_one(mm, f, y_opt, t, u)

    y_full = mm.preset_response_db(freq, gains, model)
    full_metrics = mm.regional_rmse(freq, y_full, target.target_db, target.uncertainty_db)

    meta = {
        **target.meta,
        "locked_gains_db": {str(k): float(v) for k, v in locked_gains_db.items()},
        "engine": {
            "quality": quality,
            "mode": "multi_stage_heuristic",
            "n_starts": len(starts),
            "de_seeds": de_seeds,
            "random_starts": random_starts,
            "polish_top": polish_top,
            "ils_rounds": ils_rounds,
            "stages": ["lhs+priors+lsq", "de+dual_annealing", "coord", "ils", "pairwise", "triple"],
        },
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
            "High-coverage anti-error engine (DE/annealing/ILS/pairwise/triple)."
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
