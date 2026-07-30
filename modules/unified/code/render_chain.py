"""On-demand audio chain: any bass → Azul ± RC → Mooer (live files, not historical renders)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from audio_io import TARGET_SR, load_audio, save_audio
from dsp_apply import (
    StreamingFIR,
    apply_fir,
    compare_curves,
    fir_from_magnitude,
    measure_transfer_db,
)
from paths import RepoPaths, discover_repo
from targets import azul_target


# Dense grid for FIR design (same spirit as V10.2 / RC 192 ppo).
def _dense_grid(sr: int = TARGET_SR) -> np.ndarray:
    f = 20.0 * 2.0 ** (np.arange(int(np.log2((sr / 2 - 1) / 20) * 192) + 1) / 192)
    return f[f < sr / 2]


@dataclass
class Stage:
    name: str
    frequency_hz: np.ndarray
    gain_db: np.ndarray
    meta: dict = field(default_factory=dict)


@dataclass
class ProcessResult:
    output_path: Path
    chain: list[str]
    stages: list[Stage]
    intended_freq: np.ndarray
    intended_db: np.ndarray
    fidelity: dict | None
    measure_path: Path | None
    meta: dict


def _mooer_curve_from_gains(gains: list[float], freq: np.ndarray, paths: RepoPaths) -> np.ndarray:
    import importlib.util
    import sys

    code = paths.mooer_eq / "code"
    sys.path.insert(0, str(code))
    for key in ("mooer_model",):
        if key in sys.modules:
            del sys.modules[key]
    spec = importlib.util.spec_from_file_location("mooer_model", code / "mooer_model.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["mooer_model"] = mod
    spec.loader.exec_module(mod)
    return mod.preset_response_db(freq, gains, mod.DEFAULT_MODEL)


def _load_preset_gains(preset: str | Path, paths: RepoPaths) -> tuple[list[float], dict]:
    p = Path(preset)
    if not p.is_file():
        # Convenience aliases → unified fits
        aliases = {
            "azul": paths.unified / "data" / "fits" / "azul_central_with_gain_mooer_preset.json",
            "azul_timbre": paths.unified / "data" / "fits" / "azul_central_timbre_mooer_preset.json",
            "azul+rc": paths.unified / "data" / "fits" / "azul_plus_rc_bass_with_gain_mooer_preset.json",
            "azul-rc": paths.unified / "data" / "fits" / "azul_minus_rc_bass_timbre_mooer_preset.json",
            "azul-rc_timbre": paths.unified
            / "data"
            / "fits"
            / "azul_minus_rc_bass_timbre_mooer_preset.json",
        }
        if preset in aliases:
            p = aliases[preset]
        else:
            raise FileNotFoundError(f"Unknown preset '{preset}'")
    data = json.loads(p.read_text(encoding="utf-8"))
    return list(data["gains_display_db"]), {"preset_path": str(p), **data.get("meta", {})}


def build_stages(
    chain: str,
    *,
    azul_variant: str = "central",
    include_gain: bool = True,
    rc_setup: str = "bass",
    mooer_preset: str | None = None,
    paths: RepoPaths | None = None,
    sr: int = TARGET_SR,
) -> list[Stage]:
    """Build ordered filter stages for a named chain.

    Chains (mutually exclusive semantics — no double-EQ):
      azul          → FIR Café→Azul transfer (measured curve)
      azul+rc       → Azul FIR then RC FIR (physical cascade sim)
      mooer         → single Mooer FIR from preset / alias
      rc+mooer      → RC FIR then Mooer residual preset (RC already on)
    """
    paths = paths or discover_repo()
    freq = _dense_grid(sr)
    stages: list[Stage] = []

    if chain == "azul":
        t = azul_target(variant=azul_variant, include_gain=include_gain, frequency_hz=freq, paths=paths)
        stages.append(Stage("azul", t.frequency_hz, t.target_db, t.meta))
    elif chain == "azul+rc":
        t = azul_target(variant=azul_variant, include_gain=include_gain, frequency_hz=freq, paths=paths)
        stages.append(Stage("azul", t.frequency_hz, t.target_db, t.meta))
        from bridge import load_rc

        rc = load_rc(paths)
        curves = rc.load_refined_curves()
        rc_y = np.interp(np.log(freq), np.log(curves.frequency_hz), curves.setup_db(rc_setup))
        stages.append(Stage(f"rc_{rc_setup}", freq, rc_y, {"rc_setup": rc_setup}))
    elif chain == "mooer":
        preset = mooer_preset or ("azul" if include_gain else "azul_timbre")
        gains, meta = _load_preset_gains(preset, paths)
        y = _mooer_curve_from_gains(gains, freq, paths)
        stages.append(Stage("mooer", freq, y, {**meta, "gains_display_db": gains}))
    elif chain == "rc+mooer":
        from bridge import load_rc

        rc = load_rc(paths)
        curves = rc.load_refined_curves()
        rc_y = np.interp(np.log(freq), np.log(curves.frequency_hz), curves.setup_db(rc_setup))
        stages.append(Stage(f"rc_{rc_setup}", freq, rc_y, {"rc_setup": rc_setup}))
        preset = mooer_preset or "azul-rc_timbre"
        gains, meta = _load_preset_gains(preset, paths)
        y = _mooer_curve_from_gains(gains, freq, paths)
        stages.append(Stage("mooer_residual", freq, y, {**meta, "gains_display_db": gains}))
    else:
        raise ValueError(
            f"Unknown chain '{chain}'. Use: azul | azul+rc | mooer | rc+mooer"
        )
    return stages


def combined_response(stages: list[Stage], freq: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    if not stages:
        raise ValueError("No stages")
    f = freq if freq is not None else stages[0].frequency_hz
    y = np.zeros_like(f, dtype=float)
    for st in stages:
        y = y + np.interp(np.log(f), np.log(st.frequency_hz), st.gain_db)
    return f, y


def process_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    chain: str = "azul",
    azul_variant: str = "central",
    include_gain: bool = True,
    rc_setup: str = "bass",
    mooer_preset: str | None = None,
    streaming: bool = False,
    measure: bool = True,
    numtaps: int = 8193,
    paths: RepoPaths | None = None,
) -> ProcessResult:
    """Process any bass audio through the selected chain (on-demand, not cached history)."""
    paths = paths or discover_repo()
    stages = build_stages(
        chain,
        azul_variant=azul_variant,
        include_gain=include_gain,
        rc_setup=rc_setup,
        mooer_preset=mooer_preset,
        paths=paths,
    )
    x, sr = load_audio(input_path)
    y = x.copy()
    for st in stages:
        h = fir_from_magnitude(st.frequency_hz, st.gain_db, sr=sr, numtaps=numtaps)
        if streaming:
            # align_to_same keeps measured transfer fidedigno vs intended curve;
            # for true live I/O set align_to_same=False at the StreamingFIR call site.
            y = StreamingFIR(h).process(y, align_to_same=True)
        else:
            y = apply_fir(y, h)

    out = save_audio(output_path, y, sr=sr)
    f_int, db_int = combined_response(stages)

    fidelity = None
    measure_path = None
    if measure:
        fm, hm = measure_transfer_db(x, y, sr=sr)
        fidelity = compare_curves(fm, hm, f_int, db_int)
        measure_path = Path(output_path).with_suffix("").parent / (
            Path(output_path).stem + "_measured_transfer.csv"
        )
        intended_on_m = np.interp(np.log(np.clip(fm, 1e-6, None)), np.log(f_int), db_int)
        pd.DataFrame(
            {
                "frequency_hz": fm,
                "measured_db": hm,
                "intended_db": intended_on_m,
                "error_db": hm - intended_on_m,
            }
        ).to_csv(measure_path, index=False)

    meta = {
        "input": str(input_path),
        "output": str(out),
        "sr": sr,
        "chain": chain,
        "stages": [s.name for s in stages],
        "streaming_ola": streaming,
        "numtaps": numtaps,
        "azul_variant": azul_variant,
        "include_gain": include_gain,
        "rc_setup": rc_setup,
        "mooer_preset": mooer_preset,
        "note": (
            "Curves are applied as FIR to THIS audio file on demand. "
            "Not a historical pre-render. Intended for any dry bass input."
        ),
    }
    return ProcessResult(
        output_path=out,
        chain=[s.name for s in stages],
        stages=stages,
        intended_freq=f_int,
        intended_db=db_int,
        fidelity=fidelity,
        measure_path=measure_path,
        meta=meta,
    )


def verify_against_reference(
    input_path: str | Path,
    reference_path: str | Path,
    *,
    chain: str = "azul",
    **kwargs,
) -> dict:
    """Fidelity check: apply chain to input, compare transfer to real reference.

    Reports two things:
      1) FIR fidelity vs intended curve (must be ~0 dB — DSP correctness)
      2) processed vs real reference spectrum (instrument match; static EQ limits apply)
    """
    paths = kwargs.pop("paths", None) or discover_repo()
    tmp_out = paths.unified / "_runs" / "process" / "_verify_tmp.wav"
    result = process_file(input_path, tmp_out, chain=chain, paths=paths, **kwargs)
    dry, sr = load_audio(input_path)
    ref, _ = load_audio(reference_path)
    y, _ = load_audio(result.output_path)

    # Compare transfers dry→processed vs dry→reference (same input), more honest.
    n = min(len(dry), len(ref), len(y))
    dry, ref, y = dry[:n], ref[:n], y[:n]
    f_p, h_proc = measure_transfer_db(dry, y, sr=sr)
    f_r, h_ref = measure_transfer_db(dry, ref, sr=sr)
    # Align frequency grids (welch identical length → same f).
    m = (f_p >= 40) & (f_p <= 8000)
    err = h_proc[m] - h_ref[m]
    stats = {
        "transfer_rmse_proc_vs_ref_db": float(np.sqrt(np.mean(err**2))),
        "transfer_mae_proc_vs_ref_db": float(np.mean(np.abs(err))),
        "transfer_bias_proc_vs_ref_db": float(np.mean(err)),
        "chain_fidelity_vs_intended": result.fidelity,
        "output": str(result.output_path),
        "reference": str(reference_path),
        "input": str(input_path),
        "chain": result.chain,
        "note": (
            "chain_fidelity_vs_intended ≈ 0 means the FIR applied the curve correctly. "
            "transfer_*_proc_vs_ref reflects how close a static EQ gets to the real Azul take "
            "(string/attack/non-linear residuals remain)."
        ),
    }
    report = paths.unified / "_runs" / "process" / "_verify_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    stats["report"] = str(report)
    return stats
