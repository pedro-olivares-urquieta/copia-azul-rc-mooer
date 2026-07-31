"""Local phase-curve smoother used by improve_v13."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "emulate_azul" / "code"))


def test_local_curve_recovers_flat_level():
    # Stub DENSE_F / weighted_quantile without full build import when possible.
    import improve_v13 as v13

    grid = np.geomspace(40, 400, 64)
    f = np.repeat(grid, 3)
    y = np.full_like(f, 2.5)
    w = np.ones_like(f)
    # Monkeypatch m.weighted_quantile if import pulled build_v10_2.
    med, n_eff, _ = v13._local_curve(f, y, w, grid)
    assert np.nanmean(np.abs(med - 2.5)) < 1e-9
    assert np.all(n_eff > 0)
