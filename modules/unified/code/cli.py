#!/usr/bin/env python3
"""Unified CLI: audit / summarize / fit Azul(+RC) → optimized Mooer EQ."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mooer_fit import fit_mooer_anti_error, save_fit
from orchestrate import audit, evaluate_mooer, provenance, summarize
from paths import discover_repo
from pipeline import plan
from targets import azul_rc_target, azul_target


def cmd_audit(_args: argparse.Namespace) -> int:
    df = audit()
    print(df.to_string(index=False))
    missing = int((~df.exists).sum())
    print(f"\nMissing artifacts: {missing}")
    return 1 if missing else 0


def cmd_summarize(_args: argparse.Namespace) -> int:
    summary = summarize()
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


def _print_fit(result, paths_written: dict) -> None:
    print(
        json.dumps(
            {
                "target": result.target_name,
                "gains_display_db": result.gains_display_db,
                "frequencies_hz": result.frequencies_hz,
                "global_gain_db": result.global_gain_db,
                "q_display": result.q_display,
                "anti_error_score": result.score,
                "metrics": {
                    k: result.metrics[k]
                    for k in ("worst", "avg", "global", "Subgraves", "Graves", "Medios", "Presencia", "Brillo", "ae30")
                    if k in result.metrics
                },
                "meta": result.meta,
                "written": {k: str(v) for k, v in paths_written.items()},
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_fit_azul(args: argparse.Namespace) -> int:
    """Fit Mooer EQ to the Café→Azul curve (anti-error)."""
    target = azul_target(
        variant=args.variant,
        include_gain=not args.timbre_only,
    )
    result = fit_mooer_anti_error(
        target,
        de_seeds=args.de_seeds,
        random_starts=args.random_starts,
        seed=args.seed,
    )
    out = discover_repo().unified / "data" / "fits"
    written = save_fit(result, target, out)
    _print_fit(result, written)
    return 0


def cmd_fit_azul_rc(args: argparse.Namespace) -> int:
    """Compose Azul with RC, then fit Mooer anti-error EQ.

    Default compose=minus: if RC is already on, Mooer supplies the residual
    needed to reach Azul (Azul - RC). Use --compose plus to target Azul+RC.
    """
    target = azul_rc_target(
        rc_setup=args.rc_setup,
        compose=args.compose,
        azul_variant=args.variant,
        include_gain=not args.timbre_only,
    )
    result = fit_mooer_anti_error(
        target,
        de_seeds=args.de_seeds,
        random_starts=args.random_starts,
        seed=args.seed,
    )
    out = discover_repo().unified / "data" / "fits"
    written = save_fit(result, target, out)
    _print_fit(result, written)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unified orchestrator: Azul (+ optional RC) → optimized Mooer EQ"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audit", help="Cross-module artifact audit")
    sub.add_parser("summarize", help="Build unified summary JSON/CSV")
    p = sub.add_parser("plan", help="Show runnable pipeline stages")
    p.add_argument("--allow-heavy", action="store_true")
    sub.add_parser("provenance", help="Producer→consumer edges + hashes")
    sub.add_parser("evaluate", help="Evaluate current Mooer presets vs RC curves")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--variant",
        default="central",
        choices=["central", "robust", "safe", "parametric", "total"],
        help="Azul curve variant (default: central)",
    )
    common.add_argument(
        "--timbre-only",
        action="store_true",
        help="Ignore Azul global gain; fit timbre curve only",
    )
    common.add_argument("--de-seeds", type=int, default=6)
    common.add_argument("--random-starts", type=int, default=800)
    common.add_argument("--seed", type=int, default=20260730)

    fa = sub.add_parser(
        "fit-azul",
        parents=[common],
        help="Fit Mooer GE300 to Café→Azul curve (anti-error)",
    )
    fa.set_defaults(func=cmd_fit_azul)

    far = sub.add_parser(
        "fit-azul-rc",
        parents=[common],
        help="Compose Azul with RC, then fit Mooer anti-error EQ",
    )
    far.add_argument(
        "--rc-setup",
        default="bass",
        choices=["bass", "hybrid", "guitar"],
        help="Which RC response to compose (default: bass)",
    )
    far.add_argument(
        "--compose",
        default="minus",
        choices=["minus", "plus"],
        help="minus=Azul-RC (RC already on); plus=Azul+RC cascade target",
    )
    far.set_defaults(func=cmd_fit_azul_rc)

    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        return args.func(args)
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
