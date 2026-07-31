"""Mooer model: global 1:1 range and band gain_coeff provenance."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "mooer_eq" / "code"))

import mooer_model as mm  # noqa: E402


def test_global_gain_range_and_1to1():
    grid = mm.global_gain_grid()
    assert grid[0] == -60.0
    assert grid[-1] == 3.0
    assert np.isclose(np.diff(grid).mean(), 0.5)
    f = np.array([1000.0])
    flat = mm.preset_response_db(f, [0, 0, 0, 0, 0], global_gain_db=-12.0)
    assert np.isclose(flat[0], -12.0)


def test_band_gain_uses_coeff_not_1to1():
    f = np.array([30.0])
    y = mm.bell_db(f, 30.0, 16.0)
    # At centre, bell peak ≈ gain_coeff * display.
    assert np.isclose(y[0], 0.75 * 16.0, atol=0.05)


def test_calibration_provenance_matches_coeff():
    prov = json.loads(
        (ROOT / "modules/mooer_eq/data/CALIBRATION_PROVENANCE.json").read_text(encoding="utf-8")
    )
    assert prov["display_to_effective"]["band_gain"]["gain_coeff"] == mm.DEFAULT_MODEL.gain_coeff
    assert prov["display_to_effective"]["global_gain"]["mapping"] == "1to1"
    assert prov["display_to_effective"]["global_gain"]["range_db"] == [-60.0, 3.0]


def test_clip_global_gain():
    assert mm.clip_global_gain(10) == 3.0
    assert mm.clip_global_gain(-100) == -60.0
