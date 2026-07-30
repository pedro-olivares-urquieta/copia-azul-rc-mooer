"""Import helpers that load each module's clean APIs without heavy DSP side effects."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from paths import RepoPaths, discover_repo

_SHARED_NAMES = (
    "repo_paths",
    "azul_artifacts",
    "rc_artifacts",
    "mooer_artifacts",
    "mooer_model",
)


def _purge_shared() -> None:
    for key in list(sys.modules):
        if key in _SHARED_NAMES or key.startswith("unified_"):
            del sys.modules[key]


def _load(module_file: Path, name: str) -> ModuleType:
    code_dir = str(module_file.parent.resolve())
    # Prefer this module's code directory for sibling imports like repo_paths.
    sys.path = [code_dir] + [p for p in sys.path if Path(p).resolve() != Path(code_dir).resolve()]
    _purge_shared()
    spec = importlib.util.spec_from_file_location(name, module_file)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_azul(paths: RepoPaths | None = None):
    paths = paths or discover_repo()
    return _load(paths.emulate_azul / "code" / "azul_artifacts.py", "unified_azul_artifacts")


def load_rc(paths: RepoPaths | None = None):
    paths = paths or discover_repo()
    return _load(paths.rc_pedals / "code" / "rc_artifacts.py", "unified_rc_artifacts")


def load_mooer(paths: RepoPaths | None = None):
    paths = paths or discover_repo()
    return _load(paths.mooer_eq / "code" / "mooer_artifacts.py", "unified_mooer_artifacts")
