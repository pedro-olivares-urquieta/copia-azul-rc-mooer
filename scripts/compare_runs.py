#!/usr/bin/env python3
"""Compare two emulate_azul runs (or a run against the published baseline).

    scripts/compare_runs.py det_A det_B
    scripts/compare_runs.py det_A --baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "modules" / "emulate_azul" / "_runs"
BASELINE = REPO / "modules" / "emulate_azul" / "results"

REGIONS = [
    (20, 60, "20-60"),
    (60, 250, "60-250"),
    (250, 1000, "250-1k"),
    (1000, 2000, "1k-2k"),
    (2000, 4000, "2k-4k"),
    (4000, 8000, "4k-8k"),
    (8000, 20000, "8k-20k"),
]


def results_dir(name: str) -> Path:
    if name == "__baseline__":
        return BASELINE
    d = RUNS / name / "results"
    if not d.exists():
        raise SystemExit(f"No existe {d}")
    return d


def compare(a_dir: Path, b_dir: Path, label_a: str, label_b: str) -> dict:
    a = pd.read_csv(a_dir / "CURVAS_DENSAS_V10_2.csv")
    b = pd.read_csv(b_dir / "CURVAS_DENSAS_V10_2.csv")
    f = a.frequency_hz.to_numpy()
    ca = a.precise_central_db.to_numpy()
    cb = np.interp(np.log(f), np.log(b.frequency_hz), b.precise_central_db)
    d = cb - ca

    regions = []
    for lo, hi, name in REGIONS:
        m = (f >= lo) & (f < hi)
        regions.append(
            {
                "region": name,
                "rmse_db": float(np.sqrt(np.mean(d[m] ** 2))),
                "max_abs_db": float(np.abs(d[m]).max()),
                "mean_db": float(np.mean(d[m])),
            }
        )

    out = {
        "run_a": label_a,
        "run_b": label_b,
        "curve": {
            "rmse_db": float(np.sqrt(np.mean(d**2))),
            "max_abs_db": float(np.abs(d).max()),
            "p95_abs_db": float(np.percentile(np.abs(d), 95)),
        },
        "regions": regions,
    }

    for name, cols in (
        ("GAIN_GLOBAL_V10_2.csv", None),
        ("MATCHING_EVENTOS_V10_2.csv", "rows"),
    ):
        pa, pb = a_dir / name, b_dir / name
        if not (pa.exists() and pb.exists()):
            continue
        da, db = pd.read_csv(pa), pd.read_csv(pb)
        if cols == "rows":
            out["matching_events"] = {"a": len(da), "b": len(db), "delta": len(db) - len(da)}
        else:
            out["gain"] = {
                c: {"a": float(da[c][0]), "b": float(db[c][0]), "delta": float(db[c][0] - da[c][0])}
                for c in da.columns
                if c in db.columns
            }

    for d_ in (a_dir, b_dir):
        mf = d_ / "MANIFIESTO_EJECUCION.json"
        if mf.exists():
            man = json.loads(mf.read_text())
            key = "manifest_a" if d_ is a_dir else "manifest_b"
            out[key] = {
                k: man.get(k)
                for k in ("run_id", "git_commit", "config_hash", "input_audio_hash", "output_hash")
            }

    out.update(_output_diff(a_dir, b_dir, label_a, label_b))
    out["deterministic_curve"] = out["curve"]["max_abs_db"] < 1e-9
    return out


def _output_diff(a_dir: Path, b_dir: Path, label_a: str, label_b: str) -> dict:
    """Per-file comparison, ignoring the run id embedded in recorded paths."""
    import hashlib

    def digest(path: Path, other: str, mine: str) -> str:
        data = path.read_bytes()
        if path.suffix in (".csv", ".json", ".md"):
            # The run id appears inside recorded paths; normalise it away.
            data = data.replace(mine.encode(), b"__RUN__").replace(other.encode(), b"__RUN__")
        return hashlib.sha256(data).hexdigest()

    names_a = {p.name for p in a_dir.glob("*") if p.is_file()}
    names_b = {p.name for p in b_dir.glob("*") if p.is_file()}
    skip = {"MANIFIESTO_EJECUCION.json"}
    shared = sorted((names_a & names_b) - skip)

    differing = [
        n
        for n in shared
        if digest(a_dir / n, label_b, label_a) != digest(b_dir / n, label_a, label_b)
    ]
    return {
        "outputs": {
            "compared": len(shared),
            "identical": len(shared) - len(differing),
            "differing": differing,
            "only_in_a": sorted(names_a - names_b - skip),
            "only_in_b": sorted(names_b - names_a - skip),
        },
        "bit_identical_outputs": not differing
        and not (names_a - names_b - skip)
        and not (names_b - names_a - skip),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_a")
    ap.add_argument("run_b", nargs="?")
    ap.add_argument("--baseline", action="store_true", help="compare run_a against results/")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.baseline:
        a_label, b_label = "__baseline__", args.run_a
    else:
        if not args.run_b:
            ap.error("indica run_b o usa --baseline")
        a_label, b_label = args.run_a, args.run_b

    res = compare(results_dir(a_label), results_dir(b_label), a_label, b_label)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
