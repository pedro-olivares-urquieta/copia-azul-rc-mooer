#!/usr/bin/env python3
"""Compare historical and new Mooer presets by spectral region."""
from __future__ import annotations

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from mooer_artifacts import VARIANT_ALIASES, resolve_variant
from mooer_model import DEFAULT_MODEL, preset_response_db
from repo_paths import DATA as D, curves_csv, ensure_runtime_dirs

OLD = {
    "Bajo": [15.0, 3.5, -3.5, 16.0, -3.5],
    "Híbrido": [-1.5, 3.0, 4.0, 8.5, 1.5],
    "Guitarra": [-10.0, 4.5, 3.0, 9.5, 1.0],
}
OLD30 = {
    "Bajo": [15.5, 2.0, 0.0, 12.0, -0.5],
    "Híbrido": [-1.0, 1.5, 6.5, 5.5, 4.0],
    "Guitarra": [-9.0, 3.0, 5.0, 7.5, 2.5],
}
KEY = {"Bajo": "bass", "Híbrido": "hybrid", "Guitarra": "guitar"}
REG = [
    ("Subgraves", 20, 60),
    ("Graves", 60, 250),
    ("Medios", 250, 2000),
    ("Presencia", 2000, 8000),
    ("Brillo", 8000, 15500),
]


def _gains_for(presets: pd.DataFrame, setup: str, requested: str) -> list[float] | None:
    variant = resolve_variant(presets, setup, requested)
    if variant is None:
        return None
    g = (
        presets[(presets.setup == setup) & (presets.variant == variant)]
        .sort_values("band")["gain_display_db"]
        .tolist()
    )
    return g if g else None


def main() -> None:
    ensure_runtime_dirs()
    curves = pd.read_csv(curves_csv())
    presets = pd.read_csv(D / "final_presets.csv")
    freq = curves.frequency_hz.to_numpy()

    rows = []
    for name, key in KEY.items():
        target = curves[f"{key}_recommended_analog_db"].to_numpy()
        unc = curves[f"{key}_uncertainty_db"].to_numpy()
        variants = {
            "refined_previous": OLD[name],
            "point_30hz_previous": OLD30[name],
        }
        for short in ("balanced", "subgrave", "global"):
            gains = _gains_for(presets, name, short)
            if gains is None:
                continue
            variants[f"new_{short}"] = gains

        for label, gains in variants.items():
            resp = preset_response_db(freq, gains, DEFAULT_MODEL)
            err = resp - target
            for reg, lo, hi in REG:
                m = (freq >= lo) & (freq < (hi if hi < 15500 else hi + 1))
                w = 1 / (unc[m] ** 2 + 0.12**2)
                w = w / w.sum()
                rows.append(
                    {
                        "setup": name,
                        "preset": label,
                        "region": reg,
                        "rmse": float(np.sqrt(np.sum(w * err[m] ** 2))),
                        "mae": float(np.sum(w * np.abs(err[m]))),
                        "bias": float(np.sum(w * err[m])),
                        "p95": float(np.percentile(np.abs(err[m]), 95)),
                        "max": float(np.max(np.abs(err[m]))),
                        "median_uncertainty": float(np.median(unc[m])),
                    }
                )

    r = pd.DataFrame(rows)
    r.to_csv(D / "historical_metrics_by_region.csv", index=False)

    sig = []
    for name in KEY:
        old = r[(r.setup == name) & (r.preset == "refined_previous")].set_index("region")
        new = r[(r.setup == name) & (r.preset == "new_balanced")].set_index("region")
        if new.empty:
            continue
        for reg in old.index:
            delta = new.loc[reg, "rmse"] - old.loc[reg, "rmse"]
            unc = max(old.loc[reg, "median_uncertainty"], new.loc[reg, "median_uncertainty"])
            sig.append(
                {
                    "setup": name,
                    "region": reg,
                    "old_rmse": old.loc[reg, "rmse"],
                    "new_rmse": new.loc[reg, "rmse"],
                    "delta_new_minus_old": delta,
                    "median_measurement_uncertainty": unc,
                    "change_exceeds_uncertainty": abs(delta) > unc,
                }
            )
    sig_df = pd.DataFrame(sig)
    sig_df.to_csv(D / "improvement_vs_measurement_uncertainty.csv", index=False)
    if len(sig_df):
        print(sig_df.to_string(index=False))
    else:
        print("No new_balanced variants available to compare.")


if __name__ == "__main__":
    main()
