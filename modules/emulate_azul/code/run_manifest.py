"""Execution manifest: makes every result traceable to code, config and inputs."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from repo_paths import AUDIO, MANIFEST, OUT, REPO

_TRACKED_PACKAGES = ("numpy", "scipy", "pandas", "soundfile", "librosa", "matplotlib")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def _dependency_versions() -> dict[str, str]:
    out = {}
    for name in _TRACKED_PACKAGES:
        try:
            out[name] = __import__(name).__version__
        except Exception:
            out[name] = "absent"
    return out


def _hash_dir(directory: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(directory.glob(pattern)))
    return {p.name: sha256_file(p) for p in files if p.is_file()}


def combined_hash(hashes: dict[str, str]) -> str:
    h = hashlib.sha256()
    for key in sorted(hashes):
        h.update(key.encode())
        h.update(hashes[key].encode())
    return h.hexdigest()


def build(run_id: str, *, pipeline: str, stages: list[str], extra: dict | None = None) -> dict:
    from run_config import CONFIG_PATH, config_hash, load_config

    audio_hashes = _hash_dir(AUDIO, ("*.m4a", "*.wav", "*.flac"))
    return {
        "run_id": run_id,
        "pipeline": pipeline,
        "stages": stages,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "config_path": str(CONFIG_PATH.relative_to(REPO)),
        "config_hash": config_hash(),
        "config": load_config(),
        "input_manifest": str(MANIFEST.relative_to(REPO)),
        "input_manifest_hash": sha256_file(MANIFEST),
        "input_audio_hash": combined_hash(audio_hashes),
        "input_audio_files": len(audio_hashes),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dependencies": _dependency_versions(),
        "output_dir": str(OUT),
        **(extra or {}),
    }


def write(manifest: dict, out_dir: Path = OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "MANIFIESTO_EJECUCION.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def finalize(manifest: dict, out_dir: Path = OUT) -> Path:
    """Re-write the manifest with hashes of everything the run produced."""
    outputs = {
        p.name: sha256_file(p)
        for p in sorted(out_dir.glob("*"))
        if p.is_file() and p.name != "MANIFIESTO_EJECUCION.json"
    }
    manifest = {
        **manifest,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": outputs,
        "output_hash": combined_hash(outputs),
        "n_outputs": len(outputs),
    }
    return write(manifest, out_dir)
