"""Load the versioned scientific configuration for emulate_azul."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from repo_paths import REPO

CONFIG_PATH = REPO / "config" / "emulate_azul.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def config_hash(path: Path = CONFIG_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lambdas(path: Path = CONFIG_PATH) -> tuple[tuple | None, tuple | None, list[tuple]]:
    """Return (lambda_central, lambda_robust, candidates).

    The first two are ``None`` when ``lambda_mode`` is ``cv``, which restores the
    historical—non deterministic—cross-validated selection.
    """
    reg = load_config(path).get("regularization", {})
    candidates = [tuple(c) for c in reg.get("candidates", [])]
    if str(reg.get("lambda_mode", "cv")).lower() != "fixed":
        return None, None, candidates
    return tuple(reg["lambda_central"]), tuple(reg["lambda_robust"]), candidates


def summary(path: Path = CONFIG_PATH) -> str:
    return json.dumps(load_config(path), indent=2, ensure_ascii=False)
