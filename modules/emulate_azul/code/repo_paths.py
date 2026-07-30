"""Repo-relative paths for the emulate_azul module."""
from __future__ import annotations

from pathlib import Path

CODE = Path(__file__).resolve().parent
MODULE = CODE.parent
REPO = MODULE.parents[1]
OUT = MODULE / "results"
AUD = MODULE / "renders"
WAV = MODULE / "_cache" / "wav"
LEGACY = MODULE / "legacy_curves"
EXPORTS = MODULE / "exports"
AUDIO = REPO / "audio" / "cafe_vs_azul"
MANIFEST = REPO / "manifests" / "cafe_vs_azul_pairs.csv"

# Back-compat alias used by legacy scripts.
ROOT = MODULE


def ensure_runtime_dirs() -> None:
    for d in (OUT, AUD, WAV, LEGACY, EXPORTS):
        d.mkdir(parents=True, exist_ok=True)
