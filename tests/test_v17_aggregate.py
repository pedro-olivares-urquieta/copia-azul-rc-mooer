"""Unit tests for V17 aggregation helpers (no heavy DSP)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE = Path(__file__).resolve().parents[1] / "modules" / "emulate_azul" / "code"
sys.path.insert(0, str(CODE))

import improve_v17 as v17  # noqa: E402


def test_weighted_nanmedian_prefers_high_weight():
    mat = np.array(
        [
            [0.0, 10.0],
            [2.0, 10.0],
            [20.0, 0.0],
        ],
        float,
    )
    w = np.array([1.0, 1.0, 0.01], float)
    out = v17.weighted_nanmedian(mat, w)
    assert abs(out[0] - 1.0) < 0.5  # median of 0 and 2
    assert abs(out[1] - 10.0) < 1e-9


def test_phase_repeatability_downweights_noisy_phase():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(40):
        rows.append(
            {
                "pair": "A_12",
                "phase": "sustain",
                "y_timbre": 1.0 + rng.normal(0, 0.1),
                "w": 1.0,
                "f": 1000.0,
                "family": "fret12",
            }
        )
        rows.append(
            {
                "pair": "A_12",
                "phase": "attack",
                "y_timbre": rng.normal(0, 8.0),
                "w": 1.0,
                "f": 1000.0,
                "family": "fret12",
            }
        )
    obs = pd.DataFrame(rows)
    out = v17.phase_repeatability_weights(obs)
    sus = float(out.loc[out.phase == "sustain", "rep"].iloc[0])
    att = float(out.loc[out.phase == "attack", "rep"].iloc[0])
    assert sus > att
    assert out.loc[out.phase == "attack", "w"].mean() < out.loc[out.phase == "sustain", "w"].mean()
