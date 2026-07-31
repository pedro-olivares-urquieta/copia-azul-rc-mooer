"""Repo-relative paths for the emulate_azul module.

Output locations are overridable so a reproduction run never overwrites the
published baseline in ``results/``:

    AZUL_OUT_DIR=modules/emulate_azul/_runs/<run_id>/results
    AZUL_RENDERS_DIR=modules/emulate_azul/_runs/<run_id>/renders
"""
from __future__ import annotations

import os
from pathlib import Path

CODE = Path(__file__).resolve().parent
MODULE = CODE.parent
REPO = MODULE.parents[1]


def _resolve(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    if not raw:
        return default
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (REPO / p)


OUT = _resolve("AZUL_OUT_DIR", MODULE / "results")
AUD = _resolve("AZUL_RENDERS_DIR", MODULE / "renders")
WAV = _resolve("AZUL_WAV_CACHE", MODULE / "_cache" / "wav")
LEGACY = MODULE / "legacy_curves"
EXPORTS = MODULE / "exports"
AUDIO = REPO / "audio" / "cafe_vs_azul"
MANIFEST = REPO / "manifests" / "cafe_vs_azul_pairs.csv"

# Published baseline is always readable regardless of output overrides.
BASELINE_OUT = MODULE / "results"

# Back-compat alias used by legacy scripts.
ROOT = MODULE


def ensure_runtime_dirs() -> None:
    for d in (OUT, AUD, WAV, LEGACY, EXPORTS):
        d.mkdir(parents=True, exist_ok=True)
