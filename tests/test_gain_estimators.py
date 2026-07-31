"""Gain helpers from improve_v11 must separate bulk from collapse."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "emulate_azul" / "code"))


def test_gain_estimators_bulk_vs_collapse():
    # Avoid importing build_v10_2 (heavy); exercise the pure estimator block.
    import improve_v11 as v11

    rng = np.random.default_rng(0)
    bulk = rng.normal(-11.5, 1.0, size=200)
    collapse = np.full(10, -40.0)
    z = pd.DataFrame({"g_need": np.r_[bulk, collapse]})
    z["collapsed"] = z.g_need < v11.COLLAPSE_THRESHOLD_DB
    est = v11.gain_estimators(z)
    assert est["collapsed_n"] == 10
    assert abs(est["bulk_mean_db"] - (-11.5)) < 0.3
    assert est["all_mean_db"] < est["bulk_mean_db"]
