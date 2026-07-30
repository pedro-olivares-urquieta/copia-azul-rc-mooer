"""Stage registry for the full Cafe→Azul / RC→Mooer workflow."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paths import RepoPaths, discover_repo


@dataclass(frozen=True)
class PipelineStage:
    name: str
    module: str
    command: list[str]
    inputs: list[Path]
    outputs: list[Path]
    heavy: bool
    description: str


def list_stages(paths: RepoPaths | None = None) -> list[PipelineStage]:
    paths = paths or discover_repo()
    py = "python"
    return [
        PipelineStage(
            name="emulate_azul.audit",
            module="emulate_azul",
            command=[py, str(paths.emulate_azul / "code" / "azul_cli.py"), "audit"],
            inputs=[paths.cafe_vs_azul_audio, paths.emulate_azul / "results"],
            outputs=[],
            heavy=False,
            description="Validate Azul artifacts and audio presence",
        ),
        PipelineStage(
            name="emulate_azul.build_v10_2",
            module="emulate_azul",
            command=[py, str(paths.emulate_azul / "code" / "build_v10_2.py")],
            inputs=[paths.cafe_vs_azul_audio],
            outputs=[paths.emulate_azul / "results" / "CURVAS_DENSAS_V10_2.csv"],
            heavy=True,
            description="Full Café→Azul V10.2 extraction (heavy DSP)",
        ),
        PipelineStage(
            name="rc_pedals.audit",
            module="rc_pedals",
            command=[py, str(paths.rc_pedals / "code" / "rc_cli.py"), "audit"],
            inputs=[paths.rc_audio, paths.rc_pedals / "data"],
            outputs=[],
            heavy=False,
            description="Validate RC artifacts and audio presence",
        ),
        PipelineStage(
            name="rc_pedals.reconstruct",
            module="rc_pedals",
            command=[
                py,
                str(paths.rc_pedals / "code" / "source_reconstruction_pipeline.py"),
                "--output-dir",
                str(paths.rc_pedals / "_runs" / "reconstruction"),
            ],
            inputs=[paths.rc_audio],
            outputs=[paths.rc_pedals / "data" / "refined_curves_192ppo.csv"],
            heavy=True,
            description="Full RC pink+sweep reconstruction (heavy DSP)",
        ),
        PipelineStage(
            name="mooer_eq.audit",
            module="mooer_eq",
            command=[py, str(paths.mooer_eq / "code" / "mooer_cli.py"), "audit"],
            inputs=[paths.rc_pedals / "data" / "refined_curves_192ppo.csv", paths.mooer_eq / "data"],
            outputs=[],
            heavy=False,
            description="Validate Mooer presets and upstream RC curves",
        ),
        PipelineStage(
            name="mooer_eq.optimize",
            module="mooer_eq",
            command=[py, str(paths.mooer_eq / "code" / "02_multizone_discrete_optimization.py")],
            inputs=[paths.rc_pedals / "data" / "refined_curves_192ppo.csv"],
            outputs=[paths.mooer_eq / "data" / "final_presets.csv"],
            heavy=False,
            description="Discrete multizone optimization for GE300",
        ),
        PipelineStage(
            name="mooer_eq.select",
            module="mooer_eq",
            command=[py, str(paths.mooer_eq / "code" / "04_operational_selection.py")],
            inputs=[paths.mooer_eq / "data" / "final_presets.csv"],
            outputs=[paths.mooer_eq / "data" / "PRESETS_RECOMENDADOS.json"],
            heavy=False,
            description="Operational preset selection",
        ),
        PipelineStage(
            name="unified.summarize",
            module="unified",
            command=[py, str(paths.unified / "code" / "cli.py"), "summarize"],
            inputs=[
                paths.emulate_azul / "results" / "CURVAS_DENSAS_V10_2.csv",
                paths.rc_pedals / "data" / "refined_curves_192ppo.csv",
                paths.mooer_eq / "data" / "final_presets.csv",
            ],
            outputs=[paths.unified / "data" / "unified_summary.json"],
            heavy=False,
            description="Cross-module summary report",
        ),
    ]


def plan(paths: RepoPaths | None = None, allow_heavy: bool = False):
    import pandas as pd

    paths = paths or discover_repo()
    rows = []
    for stage in list_stages(paths):
        if stage.heavy and not allow_heavy:
            action = "skip_heavy"
        else:
            missing_in = [str(p) for p in stage.inputs if not Path(p).exists()]
            action = "blocked_missing_inputs" if missing_in else "ready"
        rows.append(
            {
                "stage": stage.name,
                "module": stage.module,
                "heavy": stage.heavy,
                "action": action,
                "description": stage.description,
                "command": " ".join(stage.command),
            }
        )
    return pd.DataFrame(rows)
