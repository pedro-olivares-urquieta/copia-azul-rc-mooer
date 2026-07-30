#!/usr/bin/env python3
"""Unified CLI: audit / summarize / plan / evaluate across all modules."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrate import audit, evaluate_mooer, provenance, summarize
from paths import discover_repo
from pipeline import plan


def cmd_audit(_args: argparse.Namespace) -> int:
    df = audit()
    print(df.to_string(index=False))
    missing = int((~df.exists).sum())
    print(f"\nMissing artifacts: {missing}")
    return 1 if missing else 0


def cmd_summarize(_args: argparse.Namespace) -> int:
    summary = summarize()
    # Keep stdout readable: omit huge nested evaluation lists
    slim = {
        "artifact_audit": summary["artifact_audit"],
        "emulate_azul_gain_db": summary["modules"]["emulate_azul"]["gain_recommended_db"],
        "emulate_azul_curve_range_db": [
            summary["modules"]["emulate_azul"]["curve_min_db"],
            summary["modules"]["emulate_azul"]["curve_max_db"],
        ],
        "rc_setups": {
            k: {
                "min_db": v["min_db"],
                "max_db": v["max_db"],
                "value_at_30hz_db": v["value_at_30hz_db"],
            }
            for k, v in summary["modules"]["rc_pedals"]["setups"].items()
        },
        "mooer_recommended_gains": summary["modules"]["mooer_eq"]["recommended_gains"],
        "written": str(discover_repo().unified / "data" / "unified_summary.json"),
    }
    print(json.dumps(slim, indent=2, ensure_ascii=False))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    df = plan(allow_heavy=args.allow_heavy)
    print(df.to_string(index=False))
    return 0


def cmd_provenance(_args: argparse.Namespace) -> int:
    df = provenance()
    print(df.to_string(index=False))
    return 0


def cmd_evaluate(_args: argparse.Namespace) -> int:
    df = evaluate_mooer()
    print(df.to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unified orchestrator for emulate_azul + rc_pedals + mooer_eq"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="Cross-module artifact audit")
    sub.add_parser("summarize", help="Build unified summary JSON/CSV")
    p = sub.add_parser("plan", help="Show runnable pipeline stages")
    p.add_argument("--allow-heavy", action="store_true", help="Include heavy DSP stages as ready")
    sub.add_parser("provenance", help="Show producer→consumer artifact edges + hashes")
    sub.add_parser("evaluate", help="Evaluate Mooer recommended presets vs RC curves")
    args = parser.parse_args(argv)
    if args.cmd == "audit":
        return cmd_audit(args)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd == "provenance":
        return cmd_provenance(args)
    if args.cmd == "evaluate":
        return cmd_evaluate(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
