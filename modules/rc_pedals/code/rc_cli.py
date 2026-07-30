#!/usr/bin/env python3
"""CLI for rc_pedals artifact inspection (no heavy DSP)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rc_artifacts import audit_artifacts, summarize_curves


def cmd_audit(_args: argparse.Namespace) -> int:
    df = audit_artifacts()
    print(df.to_string(index=False))
    missing = df[~df.exists]
    if len(missing):
        print(f"\nMissing {len(missing)} required artifact(s).", file=sys.stderr)
        return 1
    print("\nAll required rc_pedals artifacts present.")
    return 0


def cmd_summarize(_args: argparse.Namespace) -> int:
    print(json.dumps(summarize_curves(), indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="rc_pedals artifact tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="Validate required data/audio artifacts")
    sub.add_parser("summarize", help="Summarize RC curves from CSVs")
    args = parser.parse_args(argv)
    if args.cmd == "audit":
        return cmd_audit(args)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
