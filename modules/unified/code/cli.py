#!/usr/bin/env python3
"""Unified CLI: audit / fit / process any bass audio through Azul±RC→Mooer."""
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
from render_chain import process_file, verify_against_reference
from report_pdf import generate_report
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
                    for k in (
                        "worst",
                        "avg",
                        "global",
                        "Subgraves",
                        "Graves",
                        "Medios",
                        "Presencia",
                        "Brillo",
                        "ae30",
                    )
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
    target = azul_target(
        variant=args.variant,
        include_gain=not args.timbre_only,
    )
    result = fit_mooer_anti_error(
        target,
        de_seeds=args.de_seeds,
        random_starts=args.random_starts,
        seed=args.seed,
        quality=getattr(args, "quality", "high"),
    )
    out = discover_repo().unified / "data" / "fits"
    written = save_fit(result, target, out)
    _print_fit(result, written)
    return 0


def cmd_fit_azul_rc(args: argparse.Namespace) -> int:
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
        quality=getattr(args, "quality", "high"),
    )
    out = discover_repo().unified / "data" / "fits"
    written = save_fit(result, target, out)
    _print_fit(result, written)
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    """Apply chain to ANY bass audio file on demand (not historical renders)."""
    paths = discover_repo()
    out = Path(args.output) if args.output else (
        paths.unified / "_runs" / "process" / f"{Path(args.input).stem}__{args.chain.replace('+', 'plus')}.wav"
    )
    result = process_file(
        args.input,
        out,
        chain=args.chain,
        azul_variant=args.variant,
        include_gain=not args.timbre_only,
        rc_setup=args.rc_setup,
        mooer_preset=args.mooer_preset,
        streaming=args.streaming,
        measure=not args.no_measure,
        numtaps=args.numtaps,
        paths=paths,
    )
    payload = {
        "mode": "on_demand_audio",
        "meta": result.meta,
        "fidelity_vs_intended_curve": result.fidelity,
        "measure_csv": str(result.measure_path) if result.measure_path else None,
        "output": str(result.output_path),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_informe(args: argparse.Namespace) -> int:
    """Generate PDF report(s): fidelity Café→Azul and/or Azul+RC→Mooer."""
    from report_azul_pdf import generate_azul_fidelity_report

    paths = discover_repo()
    mode = getattr(args, "mode", "fidelity")
    if mode in ("fidelity", "both"):
        out = (
            Path(args.output)
            if args.output and mode == "fidelity"
            else paths.repo / "INFORME_COPIA_AZUL_FIEL.pdf"
        )
        summary = generate_azul_fidelity_report(out, paths=paths)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    if mode in ("mooer", "both"):
        out = (
            Path(args.output)
            if args.output and mode == "mooer"
            else paths.repo / "INFORME_ORQUESTADOR_AZUL_RC_MOOER_V22.pdf"
        )
        summary = generate_report(
            out,
            de_seeds=args.de_seeds,
            random_starts=args.random_starts,
            seed=args.seed,
            paths=paths,
            azul_variant=getattr(args, "variant", "faithful") or "faithful",
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Process input and compare spectrum to a real reference recording."""
    stats = verify_against_reference(
        args.input,
        args.reference,
        chain=args.chain,
        azul_variant=args.variant,
        include_gain=not args.timbre_only,
        rc_setup=args.rc_setup,
        mooer_preset=args.mooer_preset,
        streaming=args.streaming,
        measure=True,
        numtaps=args.numtaps,
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    # Soft quality gate: warn (exit 0) but surface numbers clearly.
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Unified orchestrator: fit Mooer presets AND process any bass audio "
            "through Azul ± RC → Mooer on demand"
        )
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
        choices=[
            "central",
            "robust",
            "safe",
            "parametric",
            "total",
            "faithful",
            "copy",
            "operative",
        ],
        help="Azul curve variant (default: central; faithful=unsmoothed operative copy)",
    )
    common.add_argument(
        "--timbre-only",
        action="store_true",
        help="Ignore Azul global gain; fit/process timbre curve only",
    )
    common.add_argument("--de-seeds", type=int, default=12)
    common.add_argument("--random-starts", type=int, default=2500)
    common.add_argument("--seed", type=int, default=20260730)
    common.add_argument(
        "--quality",
        default="high",
        choices=["fast", "high", "max"],
        help="Search budget for anti-error engine",
    )

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

    audio_opts = argparse.ArgumentParser(add_help=False)
    audio_opts.add_argument(
        "--variant",
        default="central",
        choices=[
            "central",
            "robust",
            "safe",
            "parametric",
            "total",
            "faithful",
            "copy",
            "operative",
        ],
    )
    audio_opts.add_argument("--timbre-only", action="store_true")
    audio_opts.add_argument(
        "--rc-setup",
        default="bass",
        choices=["bass", "hybrid", "guitar"],
    )
    audio_opts.add_argument(
        "--mooer-preset",
        default=None,
        help="Preset JSON path or alias: azul|azul_timbre|azul+rc|azul-rc",
    )
    audio_opts.add_argument("--numtaps", type=int, default=8193)
    audio_opts.add_argument(
        "--streaming",
        action="store_true",
        help="Block OLA FIR (near-realtime path). Default=offline fftconvolve (highest fidelity)",
    )
    audio_opts.add_argument("--no-measure", action="store_true")

    proc = sub.add_parser(
        "process",
        parents=[audio_opts],
        help="Process ANY bass audio through Azul±RC→Mooer (on demand)",
    )
    proc.add_argument("--input", "-i", required=True, help="Any bass audio (wav/m4a/flac/…)")
    proc.add_argument("--output", "-o", default=None, help="Output wav path")
    proc.add_argument(
        "--chain",
        default="azul",
        choices=["azul", "azul+rc", "mooer", "rc+mooer"],
        help=(
            "azul=apply Café→Azul transfer; "
            "azul+rc=Azul then RC; "
            "mooer=single GE300 FIR from preset; "
            "rc+mooer=RC then Mooer residual"
        ),
    )
    proc.set_defaults(func=cmd_process)

    inf = sub.add_parser(
        "informe",
        help="PDF: copia fiel Café→Azul (default) o orquestador Azul+RC→Mooer",
    )
    inf.add_argument(
        "--mode",
        default="fidelity",
        choices=["fidelity", "mooer", "both"],
        help="fidelity=EQ fiel+curvas Café/Azul (default); mooer=presets GE300; both",
    )
    inf.add_argument(
        "--output",
        "-o",
        default=None,
        help="PDF path (default depends on --mode)",
    )
    inf.add_argument(
        "--variant",
        default="faithful",
        choices=["central", "robust", "safe", "parametric", "total", "faithful", "copy", "operative"],
        help="Azul curve for mooer mode (default: faithful = V22 operativa)",
    )
    inf.add_argument("--de-seeds", type=int, default=12)
    inf.add_argument("--random-starts", type=int, default=2500)
    inf.add_argument("--seed", type=int, default=20260730)
    inf.set_defaults(func=cmd_informe)

    ver = sub.add_parser(
        "verify",
        parents=[audio_opts],
        help="Process audio and compare spectrum to a real reference recording",
    )
    ver.add_argument("--input", "-i", required=True)
    ver.add_argument("--reference", "-r", required=True, help="Real reference audio (e.g. Azul take)")
    ver.add_argument(
        "--chain",
        default="azul",
        choices=["azul", "azul+rc", "mooer", "rc+mooer"],
    )
    ver.set_defaults(func=cmd_verify)

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
