"""Discover repo and module paths for the unified orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoPaths:
    repo: Path
    manifests: Path
    audio: Path
    emulate_azul: Path
    rc_pedals: Path
    mooer_eq: Path
    unified: Path

    @property
    def cafe_vs_azul_audio(self) -> Path:
        return self.audio / "cafe_vs_azul"

    @property
    def rc_audio(self) -> Path:
        return self.audio / "rc_response"


def discover_repo(start: Path | None = None) -> RepoPaths:
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "modules" / "emulate_azul").exists() and (candidate / "manifests").exists():
            repo = candidate
            break
    else:
        raise FileNotFoundError("Could not locate repo root from " + str(here))
    return RepoPaths(
        repo=repo,
        manifests=repo / "manifests",
        audio=repo / "audio",
        emulate_azul=repo / "modules" / "emulate_azul",
        rc_pedals=repo / "modules" / "rc_pedals",
        mooer_eq=repo / "modules" / "mooer_eq",
        unified=repo / "modules" / "unified",
    )
