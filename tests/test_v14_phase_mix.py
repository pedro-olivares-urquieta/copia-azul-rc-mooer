"""Regional phase-mix weights from V4.1 §29 must sum to 1 and favour attack in highs."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "emulate_azul" / "code"))


def test_phase_mix_sums_and_highs_prefer_attack():
    import improve_v14 as v14

    for lo, hi, *w in v14.PHASE_MIX:
        assert abs(sum(w) - 1.0) < 1e-9
    f = np.array([80.0, 400.0, 1500.0, 4000.0, 12000.0])
    att = v14._phase_mix_weight(f, np.array(["attack"] * 5))
    sus = v14._phase_mix_weight(f, np.array(["sustain"] * 5))
    # Sub-bass: sustain/body dominate attack.
    assert att[0] < sus[0]
    # Air: attack dominates sustain.
    assert att[-1] > sus[-1]
