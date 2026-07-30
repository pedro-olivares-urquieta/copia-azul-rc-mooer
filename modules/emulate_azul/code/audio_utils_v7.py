"""Minimal replacement for the missing audio_utils_v7 dependency.

Provides:
- `pairs`: Café/Azul pair descriptors pointing at normalized repo audio
- `librosa`: re-exported for onset helpers used by build_v10_2
- `periodic_grid`: simple expected-period event grid
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from repo_paths import AUDIO, MANIFEST

try:
    import librosa
except ImportError:  # optional until analysis dependencies are installed
    librosa = None

SR = 44100


def _pair_key(kind: str, label: str, position: str) -> str:
    if kind == "note":
        note = label.upper()
        if position == "open":
            return f"{note}_open"
        if position == "fret_12":
            return f"{note}_12"
        if position == "fret_24":
            return f"{note}_24"
        raise ValueError(f"Unknown note position: {position}")
    if kind == "chord":
        return label[:1].upper() + label[1:]
    if kind == "chromatic":
        return f"{label.upper()}_chromatic"
    raise ValueError(f"Unknown kind: {kind}")


def _declared_kind(kind: str) -> str:
    if kind == "note":
        return "mono"
    return kind


def load_pairs(
    manifest: Path = MANIFEST,
    audio_dir: Path = AUDIO,
    require_audio: bool = True,
) -> list[dict]:
    rows = []
    with manifest.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = _pair_key(r["kind"], r["label"], r["position"])
            cafe = audio_dir / Path(r["cafe_path"]).name
            azul = audio_dir / Path(r["azul_path"]).name
            if require_audio and (not cafe.exists() or not azul.exists()):
                raise FileNotFoundError(f"Missing audio for pair {key}: {cafe} / {azul}")
            rows.append(
                {
                    "key": key,
                    "kind": _declared_kind(r["kind"]),
                    "cafe": str(cafe),
                    "azul": str(azul),
                    "pair_id": r["pair_id"],
                }
            )
    rows.sort(key=lambda p: p["key"])
    return rows


_pairs_cache: list[dict] | None = None


def get_pairs(require_audio: bool = True) -> list[dict]:
    global _pairs_cache
    if _pairs_cache is None:
        _pairs_cache = load_pairs(require_audio=require_audio)
    return _pairs_cache


def __getattr__(name: str):
    if name == "pairs":
        return get_pairs(require_audio=True)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def periodic_grid(y: np.ndarray, expected_period: float, sr: int = SR):
    """Return a simple periodic time grid covering the signal duration."""
    y = np.asarray(y, dtype=float)
    duration = len(y) / float(sr)
    if expected_period <= 0:
        raise ValueError("expected_period must be > 0")
    # Start slightly after silence using a coarse energy threshold.
    frame = max(1, int(0.02 * sr))
    energy = np.array([np.mean(y[i : i + frame] ** 2) for i in range(0, max(len(y) - frame, 1), frame)])
    thr = max(np.median(energy) * 3.0, 1e-10)
    start_frame = int(np.argmax(energy > thr)) if np.any(energy > thr) else 0
    t0 = start_frame * frame / sr
    times = np.arange(t0, max(duration - 0.05, t0), expected_period)
    if len(times) == 0:
        times = np.array([min(0.25, duration * 0.1)], dtype=float)
    return times, float(expected_period), int(len(times))
