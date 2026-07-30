"""Repo-relative paths for the mooer_eq module."""
from __future__ import annotations

from pathlib import Path

CODE = Path(__file__).resolve().parent
MODULE = CODE.parent
REPO = MODULE.parents[1]
DATA = MODULE / "data"
CONFIG = MODULE / "config"
DOCS = MODULE / "docs"
PLOTS = MODULE / "plots"
RC_DATA = MODULE.parent / "rc_pedals" / "data"


def ensure_runtime_dirs() -> None:
    for d in (DATA, CONFIG, PLOTS):
        d.mkdir(parents=True, exist_ok=True)


def curves_csv() -> Path:
    """Prefer local copy, otherwise read from rc_pedals results."""
    local = DATA / "refined_curves_192ppo.csv"
    if local.exists():
        return local
    remote = RC_DATA / "refined_curves_192ppo.csv"
    if remote.exists():
        return remote
    raise FileNotFoundError(
        "Missing refined_curves_192ppo.csv in mooer_eq/data or rc_pedals/data"
    )
