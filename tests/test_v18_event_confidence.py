"""Unit tests for V18 event-confidence helpers (no heavy DSP)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE = Path(__file__).resolve().parents[1] / "modules" / "emulate_azul" / "code"
sys.path.insert(0, str(CODE))


def test_class_weights_prefer_clean():
    import improve_v18 as v18

    assert v18.CLASS_W["clean"] > v18.CLASS_W["overlap"]
    assert v18.CLASS_W["tight"] > v18.CLASS_W["crowded"]


def test_phase_first_mix_finite_on_synthetic():
    import improve_v14 as v14
    import improve_v18 as v18

    rng = np.random.default_rng(1)
    rows = []
    for phase, base in (("attack", 4.0), ("sustain", 3.0), ("body", 2.5)):
        for i in range(30):
            f = float(200 * 2 ** (i / 12))
            rows.append(
                {
                    "pair": "A_12",
                    "phase": phase,
                    "f": f,
                    "y_timbre": base + 0.1 * rng.normal(),
                    "w": 1.0,
                    "family": "fret12",
                }
            )
    obs = pd.DataFrame(rows)
    curve, agree = v18.phase_first_pair_curve(obs, "A_12")
    assert np.isfinite(curve).mean() > 0.5
    assert np.all((agree >= 0) & (agree <= 1))
    # Attack/sustain disagree by ~1 dB → agreement not 1 everywhere.
    assert float(np.nanmedian(agree)) < 0.99
