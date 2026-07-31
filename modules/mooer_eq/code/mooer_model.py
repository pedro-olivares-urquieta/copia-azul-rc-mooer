"""Shared Mooer GE300 EQ model (calibrated display → effective response)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class MooerModel:
    frequencies_hz: tuple[float, ...] = (30.0, 148.0, 735.0, 3637.0, 18000.0)
    q_display: float = 0.3
    # Global gain is additive 1:1 in dB (not scaled by gain_coeff).
    global_gain_db: float = 3.0
    global_gain_min_db: float = -60.0
    global_gain_max_db: float = 3.0
    global_gain_step_db: float = 0.5
    # Per-band display gains.
    gain_min_db: float = -16.0
    gain_max_db: float = 16.0
    gain_step_db: float = 0.5
    # Display→effective for band gains only. Provenance:
    # modules/mooer_eq/data/CALIBRATION_PROVENANCE.json
    gain_coeff: float = 0.75
    q_base: float = 0.569
    q_gain_slope: float = -0.0026


DEFAULT_MODEL = MooerModel()
REGIONS = (
    ("Subgraves", 20.0, 60.0),
    ("Graves", 60.0, 250.0),
    ("Medios", 250.0, 2000.0),
    ("Presencia", 2000.0, 8000.0),
    ("Brillo", 8000.0, 15500.0),
)


def gain_effective(gain_display_db: float | np.ndarray, model: MooerModel = DEFAULT_MODEL) -> np.ndarray:
    return model.gain_coeff * np.asarray(gain_display_db, dtype=float)


def q_effective(gain_display_db: float | np.ndarray, model: MooerModel = DEFAULT_MODEL) -> np.ndarray:
    g = np.asarray(gain_display_db, dtype=float)
    return model.q_display * (model.q_base + model.q_gain_slope * g)


def global_gain_grid(model: MooerModel = DEFAULT_MODEL) -> np.ndarray:
    """Hardware global gain range (−60…+3 dB), 1:1 with response dB."""
    return np.arange(
        model.global_gain_min_db,
        model.global_gain_max_db + 1e-9,
        model.global_gain_step_db,
    )


def clip_global_gain(gain_db: float, model: MooerModel = DEFAULT_MODEL) -> float:
    return float(np.clip(gain_db, model.global_gain_min_db, model.global_gain_max_db))


def bell_db(
    freq_hz: np.ndarray,
    center_hz: float,
    gain_display_db: float,
    model: MooerModel = DEFAULT_MODEL,
) -> np.ndarray:
    f = np.asarray(freq_hz, dtype=float)
    g = float(gain_display_db)
    A = 10 ** (model.gain_coeff * g / 40.0)
    q = float(q_effective(g, model))
    r = f / center_hz
    num = (1 - r * r) ** 2 + (A * r / q) ** 2
    den = (1 - r * r) ** 2 + (r / (A * q)) ** 2
    return 10 * np.log10(num / den)


def preset_response_db(
    freq_hz: np.ndarray,
    gains_display_db: Sequence[float],
    model: MooerModel = DEFAULT_MODEL,
    global_gain_db: float | None = None,
) -> np.ndarray:
    gains = list(gains_display_db)
    if len(gains) != len(model.frequencies_hz):
        raise ValueError(
            f"Expected {len(model.frequencies_hz)} gains, got {len(gains)}"
        )
    g0 = model.global_gain_db if global_gain_db is None else clip_global_gain(global_gain_db, model)
    y = np.full_like(np.asarray(freq_hz, dtype=float), g0)
    for fc, g in zip(model.frequencies_hz, gains):
        y = y + bell_db(freq_hz, fc, g, model)
    return y


def regional_rmse(
    freq_hz: np.ndarray,
    response_db: np.ndarray,
    target_db: np.ndarray,
    uncertainty_db: np.ndarray | None = None,
) -> dict[str, float]:
    f = np.asarray(freq_hz, dtype=float)
    e = np.asarray(response_db, dtype=float) - np.asarray(target_db, dtype=float)
    u = (
        np.asarray(uncertainty_db, dtype=float)
        if uncertainty_db is not None
        else np.full_like(f, 0.12)
    )
    out: dict[str, float] = {}
    region_rmses = []
    for name, lo, hi in REGIONS:
        m = (f >= lo) & (f < (hi if hi < 15500 else hi + 1))
        w = 1.0 / (u[m] ** 2 + 0.12**2)
        w = w / w.sum()
        rmse = float(np.sqrt(np.sum(w * e[m] ** 2)))
        out[name] = rmse
        region_rmses.append(rmse)
    w = 1.0 / (u**2 + 0.12**2)
    w *= np.where(f <= 15500, 1.0, np.clip((18000 - f) / 2500, 0.05, 1.0))
    w = w / w.sum()
    out["worst"] = float(max(region_rmses))
    out["avg"] = float(np.mean(region_rmses))
    out["global"] = float(np.sqrt(np.sum(w * e**2)))
    return out
