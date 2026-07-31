"""Tonal proximity peaks on harmonics and stays elevated for residuals."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "emulate_azul" / "code"))


def test_tonal_proximity_on_harmonic():
    import improve_v15 as v15

    f0 = np.array([100.0, 100.0, 100.0])
    f = np.array([100.0, 200.0, 150.0])  # fund, H2, between
    kind = np.array(["fundamental", "tonal_harmonic", "tonal_harmonic"])
    p = v15.tonal_proximity(f, f0, kind)
    assert p[0] > 0.9
    assert p[1] > 0.9
    assert p[2] < p[1]
