"""Cross-module audit / summarize / evaluate logic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from bridge import load_azul, load_mooer, load_rc
from paths import RepoPaths, discover_repo
from pipeline import plan


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit(paths: RepoPaths | None = None) -> pd.DataFrame:
    paths = paths or discover_repo()
    azul = load_azul(paths)
    rc = load_rc(paths)
    mooer = load_mooer(paths)
    frames = [
        azul.audit_artifacts().assign(module="emulate_azul"),
        rc.audit_artifacts().assign(module="rc_pedals"),
        mooer.audit_artifacts().assign(module="mooer_eq"),
    ]
    return pd.concat(frames, ignore_index=True)


def provenance(paths: RepoPaths | None = None) -> pd.DataFrame:
    paths = paths or discover_repo()
    rows = []
    rc_curves = paths.rc_pedals / "data" / "refined_curves_192ppo.csv"
    mooer_presets = paths.mooer_eq / "data" / "final_presets.csv"
    azul_curve = paths.emulate_azul / "results" / "CURVAS_DENSAS_V10_2.csv"
    edges = [
        ("rc_pedals", rc_curves, "mooer_eq", mooer_presets, "RC curves feed Mooer optimization"),
        ("emulate_azul", azul_curve, "unified", paths.unified / "data" / "unified_summary.json", "Azul curve feeds unified summary"),
        ("rc_pedals", rc_curves, "unified", paths.unified / "data" / "unified_summary.json", "RC curves feed unified summary"),
        ("mooer_eq", mooer_presets, "unified", paths.unified / "data" / "unified_summary.json", "Mooer presets feed unified summary"),
    ]
    for producer, src, consumer, dst, note in edges:
        rows.append(
            {
                "producer": producer,
                "source": str(src),
                "source_exists": src.exists(),
                "source_sha256": sha256_file(src) if src.exists() else None,
                "consumer": consumer,
                "target": str(dst),
                "target_exists": dst.exists(),
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def summarize(paths: RepoPaths | None = None) -> dict:
    paths = paths or discover_repo()
    azul = load_azul(paths)
    rc = load_rc(paths)
    mooer = load_mooer(paths)
    audit_df = audit(paths)
    prov = provenance(paths)
    summary = {
        "modules": {
            "emulate_azul": azul.summarize_curve(),
            "rc_pedals": rc.summarize_curves(),
            "mooer_eq": mooer.summarize(),
        },
        "artifact_audit": {
            "total": int(len(audit_df)),
            "missing": int((~audit_df.exists).sum()),
            "missing_items": audit_df.loc[~audit_df.exists, ["module", "artifact", "path"]].to_dict("records"),
        },
        "provenance": prov.to_dict("records"),
        "pipeline_plan_no_heavy": plan(paths, allow_heavy=False).to_dict("records"),
    }
    out_dir = paths.unified / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "unified_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    audit_df.to_csv(out_dir / "unified_artifact_audit.csv", index=False)
    prov.to_csv(out_dir / "pipeline_edges.csv", index=False)
    return summary


def evaluate_mooer(paths: RepoPaths | None = None) -> pd.DataFrame:
    paths = paths or discover_repo()
    mooer = load_mooer(paths)
    df = mooer.evaluate_recommended()
    out = paths.unified / "data"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "mooer_evaluation.csv", index=False)
    return df
