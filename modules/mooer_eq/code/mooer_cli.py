#!/usr/bin/env python3
"""CLI for mooer_eq artifact inspection and evaluation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mooer_artifacts import audit_artifacts, evaluate_recommended, summarize


def cmd_audit(_args: argparse.Namespace) -> int:
    df = audit_artifacts()
    print(df.to_string(index=False))
    missing = df[~df.exists]
    if len(missing):
        print(f"\nMissing {len(missing)} required artifact(s).", file=sys.stderr)
        return 1
    print("\nAll required mooer_eq artifacts present.")
    return 0


def cmd_summarize(_args: argparse.Namespace) -> int:
    print(json.dumps(summarize(), indent=2, ensure_ascii=False))
    return 0


def cmd_evaluate(_args: argparse.Namespace) -> int:
    df = evaluate_recommended()
    print(df.to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mooer_eq artifact tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="Validate required data artifacts")
    sub.add_parser("summarize", help="Summarize recommended presets")
    sub.add_parser("evaluate", help="Evaluate recommended presets vs RC curves")
    args = parser.parse_args(argv)
    if args.cmd == "audit":
        return cmd_audit(args)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    if args.cmd == "evaluate":
        return cmd_evaluate(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
