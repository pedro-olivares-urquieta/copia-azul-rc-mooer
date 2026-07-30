"""Repo-relative paths for the rc_pedals module."""
from __future__ import annotations

from pathlib import Path

CODE = Path(__file__).resolve().parent
MODULE = CODE.parent
REPO = MODULE.parents[1]
DATA = MODULE / "data"
CONFIG = MODULE / "config"
DOCS = MODULE / "docs"
CHECKSUMS = MODULE / "checksums"
PLOTS = MODULE / "plots"
LOGS = MODULE / "logs"
CACHE = MODULE / "_cache"
WAV_CACHE = CACHE / "wav"
AUDIO_DIR = REPO / "audio" / "rc_response"

# Legacy logical names used in existing CSVs / pipeline code → normalized repo files.
AUDIO_FILES = {
    "Pink.m4a": AUDIO_DIR / "pink__off.m4a",
    "Pink rc bass on.m4a": AUDIO_DIR / "pink__rc_bass.m4a",
    "Pink rc hybrid on.m4a": AUDIO_DIR / "pink__rc_hybrid.m4a",
    "Pink rc guitar on.m4a": AUDIO_DIR / "pink__rc_guitar.m4a",
    "1 22k.m4a": AUDIO_DIR / "sweep_1_22k__off.m4a",
    "1 22k rc bass on.m4a": AUDIO_DIR / "sweep_1_22k__rc_bass.m4a",
    "1 22k rc hybrid on.m4a": AUDIO_DIR / "sweep_1_22k__rc_hybrid.m4a",
    "1 22k rc guitar on.m4a": AUDIO_DIR / "sweep_1_22k__rc_guitar.m4a",
}


def ensure_runtime_dirs() -> None:
    for d in (DATA, CONFIG, PLOTS, LOGS, CACHE, WAV_CACHE):
        d.mkdir(parents=True, exist_ok=True)


def audio_path(legacy_name: str) -> Path:
    path = AUDIO_FILES[legacy_name]
    if not path.exists():
        raise FileNotFoundError(f"Missing RC audio for {legacy_name}: {path}")
    return path
