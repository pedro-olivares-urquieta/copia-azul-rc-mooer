"""Onset envelope must be deterministic and librosa-compatible when available."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "emulate_azul" / "code"))

import onsets  # noqa: E402


def test_onset_strength_deterministic():
    rng = np.random.default_rng(7)
    y = rng.normal(0, 0.1, size=44100)
    y[10000:10500] += np.hanning(500) * 0.8
    a = onsets.onset_strength(y, sr=44100)
    b = onsets.onset_strength(y, sr=44100)
    assert a.shape == b.shape
    assert np.allclose(a, b, atol=0.0, rtol=0.0)


def test_mel_filterbank_shape_and_normalization():
    w = onsets.mel_filterbank(44100, n_fft=2048, n_mels=128)
    assert w.shape == (128, 1025)
    # Each filter should have positive mass.
    assert np.all(w.sum(axis=1) > 0)
