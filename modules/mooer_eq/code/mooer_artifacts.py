"""Artifact loaders / evaluators for mooer_eq (CSV-first)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mooer_model import DEFAULT_MODEL, preset_response_db, regional_rmse
from repo_paths import DATA, curves_csv


REQUIRED = [
    "final_presets.csv",
    "PRESETS_RECOMENDADOS.json",
    "results_summary.json",
    "final_preset_selection_metrics.csv",
    "final_metrics_by_region.csv",
]


SETUP_KEYS = {"Bajo": "bass", "Híbrido": "hybrid", "Guitarra": "guitar"}
VARIANT_ALIASES = {
    "balanced": "balanced_recommended",
    "subgrave": "subgrave_alternative",
    "global": "global_rmse_audit",
    "minimax": "minimax_regional_audit",
    "balanced_recommended": "balanced_recommended",
    "subgrave_alternative": "subgrave_alternative",
    "global_rmse_audit": "global_rmse_audit",
    "minimax_regional_audit": "minimax_regional_audit",
}


def load_presets(data_dir: Path = DATA) -> pd.DataFrame:
    return pd.read_csv(data_dir / "final_presets.csv")


def recommended_gains(data_dir: Path = DATA) -> dict[str, list[float]]:
    presets = load_presets(data_dir)
    out = {}
    for setup in ("Bajo", "Híbrido", "Guitarra"):
        variant = "balanced_recommended"
        if not ((presets.setup == setup) & (presets.variant == variant)).any():
            # fallback to any available variant for setup
            sub = presets[presets.setup == setup]
            if sub.empty:
                continue
            variant = sub.variant.iloc[0]
        g = (
            presets[(presets.setup == setup) & (presets.variant == variant)]
            .sort_values("band")["gain_display_db"]
            .tolist()
        )
        out[setup] = g
    return out


def resolve_variant(presets: pd.DataFrame, setup: str, requested: str) -> str | None:
    name = VARIANT_ALIASES.get(requested, requested)
    if ((presets.setup == setup) & (presets.variant == name)).any():
        return name
    # try reverse aliases
    for alias, canonical in VARIANT_ALIASES.items():
        if canonical == name and ((presets.setup == setup) & (presets.variant == alias)).any():
            return alias
    return None


def evaluate_recommended(data_dir: Path = DATA) -> pd.DataFrame:
    curves = pd.read_csv(curves_csv())
    freq = curves.frequency_hz.to_numpy()
    presets = load_presets(data_dir)
    rows = []
    for setup_name, key in SETUP_KEYS.items():
        variant = resolve_variant(presets, setup_name, "balanced_recommended")
        if variant is None:
            continue
        gains = (
            presets[(presets.setup == setup_name) & (presets.variant == variant)]
            .sort_values("band")["gain_display_db"]
            .tolist()
        )
        target = curves[f"{key}_recommended_analog_db"].to_numpy()
        unc = curves[f"{key}_uncertainty_db"].to_numpy()
        resp = preset_response_db(freq, gains, DEFAULT_MODEL)
        metrics = regional_rmse(freq, resp, target, unc)
        rows.append(
            {
                "setup": setup_name,
                "variant": variant,
                "gains_db": gains,
                **metrics,
                "error_30hz_db": float(resp[np.argmin(np.abs(freq - 30))] - target[np.argmin(np.abs(freq - 30))]),
            }
        )
    return pd.DataFrame(rows)


def audit_artifacts(data_dir: Path = DATA) -> pd.DataFrame:
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
    cpath = curves_csv()
    rows.append(
        {
            "artifact": "refined_curves_192ppo.csv",
            "path": str(cpath),
            "exists": cpath.exists(),
            "bytes": cpath.stat().st_size if cpath.exists() else 0,
            "kind": "upstream_rc",
        }
    )
    return pd.DataFrame(rows)


def summarize(data_dir: Path = DATA) -> dict:
    import json

    summary = json.loads((data_dir / "results_summary.json").read_text(encoding="utf-8"))
    eval_df = evaluate_recommended(data_dir)
    return {
        "results_summary": summary,
        "recommended_gains": recommended_gains(data_dir),
        "evaluated_metrics": eval_df.to_dict("records"),
        "model": {
            "frequencies_hz": list(DEFAULT_MODEL.frequencies_hz),
            "q_display": DEFAULT_MODEL.q_display,
            "global_gain_db": DEFAULT_MODEL.global_gain_db,
        },
    }
