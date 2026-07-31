"""Artifact loaders and validators for emulate_azul (CSV-first, no heavy DSP)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from repo_paths import OUT, AUDIO, MANIFEST, LEGACY, MODULE


REQUIRED = [
    "CURVAS_DENSAS_V10_2.csv",
    "GAIN_GLOBAL_V10_2.csv",
    "GAIN_POR_PAREJA_Y_FUENTE_V10_2.csv",
    "PRESET_PARAMETRICO_V10_2.csv",
    "QUE_CONTIENEN_REALMENTE_LOS_AUDIOS_V10_2.csv",
    "CONFIG_V10_2.json",
]

FAITHFUL_VARIANTS = frozenset({"faithful", "copy", "operative"})


@dataclass
class AzulTransferCurve:
    frequency_hz: np.ndarray
    central_db: np.ndarray
    robust_db: np.ndarray
    safe_db: np.ndarray
    parametric_db: np.ndarray
    total_central_with_gain_db: np.ndarray | None
    support_state: np.ndarray | None
    faithful_db: np.ndarray | None = None

    def interpolate(self, freqs: np.ndarray, variant: str = "central") -> np.ndarray:
        mapping = {
            "central": self.central_db,
            "robust": self.robust_db,
            "safe": self.safe_db,
            "parametric": self.parametric_db,
            "total": self.total_central_with_gain_db
            if self.total_central_with_gain_db is not None
            else self.central_db,
            "faithful": self.faithful_db
            if self.faithful_db is not None
            else self.central_db,
            "copy": self.faithful_db
            if self.faithful_db is not None
            else self.central_db,
            "operative": self.faithful_db
            if self.faithful_db is not None
            else self.central_db,
        }
        if variant not in mapping:
            raise ValueError(f"Unknown variant {variant}; choose from {sorted(mapping)}")
        y = mapping[variant]
        if y is None:
            raise ValueError(f"Variant {variant} has no curve data in this results dir")
        return np.interp(np.log(freqs), np.log(self.frequency_hz), y)


def resolve_results_dir(results_dir: Path | None = None) -> Path:
    """Prefer explicit/env OUT; else newest `_runs/*/results` with operative curve."""
    import os

    if results_dir is not None:
        return Path(results_dir)
    if os.environ.get("AZUL_OUT_DIR"):
        return OUT
    if (OUT / "CURVA_COPIA_OPERATIVA.csv").exists():
        return OUT
    runs = MODULE / "_runs"
    cands = [
        p
        for p in runs.glob("*/results")
        if (p / "CURVA_COPIA_OPERATIVA.csv").exists()
    ] if runs.is_dir() else []
    if cands:
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return cands[0]
    det_a = MODULE / "_runs" / "det_A" / "results"
    if (det_a / "CURVA_COPIA_OPERATIVA.csv").exists():
        return det_a
    return OUT


def load_curve(results_dir: Path | None = None) -> AzulTransferCurve:
    results_dir = resolve_results_dir(results_dir)
    # Published V10.2 baseline always readable for structural variants.
    baseline = MODULE / "results"
    path = results_dir / "CURVAS_DENSAS_V10_2.csv"
    if not path.exists():
        path = baseline / "CURVAS_DENSAS_V10_2.csv"
    df = pd.read_csv(path)
    total = df["total_central_with_gain_db"].to_numpy() if "total_central_with_gain_db" in df else None
    support = df["support_state"].to_numpy() if "support_state" in df else None

    faithful = None
    op = results_dir / "CURVA_COPIA_OPERATIVA.csv"
    if not op.exists():
        op = MODULE / "_runs" / "det_A" / "results" / "CURVA_COPIA_OPERATIVA.csv"
    if op.exists():
        op_df = pd.read_csv(op)
        col = "eq_copy_db" if "eq_copy_db" in op_df.columns else op_df.columns[1]
        faithful = np.interp(
            np.log(df["frequency_hz"].to_numpy()),
            np.log(op_df["frequency_hz"].to_numpy()),
            op_df[col].to_numpy(float),
        )

    return AzulTransferCurve(
        frequency_hz=df["frequency_hz"].to_numpy(),
        central_db=df["precise_central_db"].to_numpy(),
        robust_db=df["precise_robust_db"].to_numpy(),
        safe_db=df["safe_db"].to_numpy(),
        parametric_db=df["parametric_db"].to_numpy(),
        total_central_with_gain_db=total,
        support_state=support,
        faithful_db=faithful,
    )


def load_gain(results_dir: Path | None = None, *, variant: str = "central") -> pd.DataFrame:
    results_dir = resolve_results_dir(results_dir)
    if variant in FAITHFUL_VARIANTS:
        gain_csv = results_dir / "GAIN_COPIA_OPERATIVA.csv"
        if not gain_csv.exists():
            gain_csv = MODULE / "_runs" / "det_A" / "results" / "GAIN_COPIA_OPERATIVA.csv"
        if gain_csv.exists():
            return pd.read_csv(gain_csv)
        for name in ("IMPLEMENTACION_FIEL_V17.json", "IMPLEMENTACION_FIEL_V16.json"):
            impl = results_dir / name
            if not impl.exists():
                impl = MODULE / "_runs" / "det_A" / "results" / name
            if impl.exists():
                data = json.loads(impl.read_text(encoding="utf-8"))
                return pd.DataFrame(
                    [
                        {
                            "gain_recommended_db": float(data["gain_db"]),
                            "gain_source": data.get("operative_variant", name),
                            "pipeline_version": data.get("version", ""),
                        }
                    ]
                )
    path = results_dir / "GAIN_GLOBAL_V10_2.csv"
    if not path.exists():
        path = MODULE / "results" / "GAIN_GLOBAL_V10_2.csv"
    return pd.read_csv(path)


def load_parametric_preset(results_dir: Path = OUT) -> pd.DataFrame:
    return pd.read_csv(results_dir / "PRESET_PARAMETRICO_V10_2.csv")


def summarize_curve(results_dir: Path = OUT) -> dict:
    curve = load_curve(results_dir)
    gain = load_gain(results_dir).iloc[0]
    key_freqs = [30.87, 41.2, 55, 80, 120, 250, 500, 800, 1000, 1250, 1600, 2000, 3150, 5000, 8000]
    points = {
        f"{f:g}Hz": float(curve.interpolate(np.array([f]), "central")[0]) for f in key_freqs
    }
    return {
        "gain_recommended_db": float(gain["gain_recommended_db"]),
        "gain_ci95_low_db": float(gain.get("ci95_low_db", np.nan)),
        "gain_ci95_high_db": float(gain.get("ci95_high_db", np.nan)),
        "curve_min_db": float(np.nanmin(curve.central_db)),
        "curve_max_db": float(np.nanmax(curve.central_db)),
        "key_points_central_db": points,
        "legacy_v9_available": (LEGACY / "curva_v9_puntos.csv").exists(),
        "legacy_v10_1_available": (LEGACY / "curva_v10_1_densa.csv").exists(),
    }


def audit_artifacts(results_dir: Path = OUT, audio_dir: Path = AUDIO) -> pd.DataFrame:
    rows = []
    for name in REQUIRED:
        path = results_dir / name
        rows.append(
            {
                "artifact": name,
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "kind": "result",
            }
        )
    n_audio = len(list(audio_dir.glob("*.m4a"))) if audio_dir.exists() else 0
    rows.append(
        {
            "artifact": "cafe_vs_azul_m4a",
            "path": str(audio_dir),
            "exists": n_audio >= 32,
            "bytes": n_audio,
            "kind": "audio_count",
        }
    )
    rows.append(
        {
            "artifact": "pair_manifest",
            "path": str(MANIFEST),
            "exists": MANIFEST.exists(),
            "bytes": MANIFEST.stat().st_size if MANIFEST.exists() else 0,
            "kind": "manifest",
        }
    )
    return pd.DataFrame(rows)
