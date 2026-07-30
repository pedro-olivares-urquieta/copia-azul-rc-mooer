"""Artifact loaders and validators for rc_pedals (CSV-first)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from repo_paths import DATA, AUDIO_DIR, AUDIO_FILES


REQUIRED = [
    "refined_curves_192ppo.csv",
    "refined_curves_384ppo_audit.csv",
    "audio_qc.csv",
    "method_validation.csv",
    "grid_convergence_192_vs_384.csv",
]


@dataclass
class RcCurveSet:
    frequency_hz: np.ndarray
    setups: dict[str, np.ndarray]
    uncertainties: dict[str, np.ndarray]

    def setup_db(self, setup: str) -> np.ndarray:
        return self.setups[setup]


def load_refined_curves(path: Path | None = None) -> RcCurveSet:
    path = path or (DATA / "refined_curves_192ppo.csv")
    df = pd.read_csv(path)
    setups = {}
    uncs = {}
    for setup in ("bass", "hybrid", "guitar"):
        col = f"{setup}_recommended_analog_db"
        ucol = f"{setup}_uncertainty_db"
        if col not in df.columns:
            raise KeyError(f"Missing column {col} in {path}")
        setups[setup] = df[col].to_numpy()
        uncs[setup] = df[ucol].to_numpy() if ucol in df.columns else np.full(len(df), np.nan)
    return RcCurveSet(frequency_hz=df["frequency_hz"].to_numpy(), setups=setups, uncertainties=uncs)


def summarize_curves(data_dir: Path = DATA) -> dict:
    curves = load_refined_curves(data_dir / "refined_curves_192ppo.csv")
    conv = pd.read_csv(data_dir / "grid_convergence_192_vs_384.csv")
    out = {"setups": {}}
    for setup, y in curves.setups.items():
        u = curves.uncertainties[setup]
        out["setups"][setup] = {
            "mean_db": float(np.nanmean(y)),
            "min_db": float(np.nanmin(y)),
            "max_db": float(np.nanmax(y)),
            "median_uncertainty_db": float(np.nanmedian(u)),
            "value_at_30hz_db": float(np.interp(30, curves.frequency_hz, y)),
        }
    high = conv[conv["range"].str.contains("20-15500", na=False)]
    out["grid_convergence_20_15500"] = (
        high[["setup", "rmse_difference_db", "p95_abs_difference_db"]].to_dict("records")
        if len(high)
        else []
    )
    return out


def audit_artifacts(data_dir: Path = DATA, audio_dir: Path = AUDIO_DIR) -> pd.DataFrame:
    rows = []
    for name in REQUIRED:
        path = data_dir / name
        rows.append(
            {
                "artifact": name,
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "kind": "data",
            }
        )
    for legacy, path in AUDIO_FILES.items():
        rows.append(
            {
                "artifact": legacy,
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "kind": "audio",
            }
        )
    rows.append(
        {
            "artifact": "audio_dir",
            "path": str(audio_dir),
            "exists": audio_dir.exists(),
            "bytes": len(list(audio_dir.glob("*.m4a"))) if audio_dir.exists() else 0,
            "kind": "audio_count",
        }
    )
    return pd.DataFrame(rows)
