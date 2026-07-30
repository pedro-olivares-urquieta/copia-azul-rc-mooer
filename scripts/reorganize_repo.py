#!/usr/bin/env python3
"""One-shot reorganization of copia-azul-rc-mooer into normalized modules."""

from __future__ import annotations

import csv
import hashlib
import shutil
import unicodedata
from pathlib import Path

ROOT = Path("/workspace")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs(paths: list[Path]) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def normalize_cafe_azul() -> list[dict]:
    src_dir = ROOT / "Azul vs cafe-20260730T193323Z-1-001" / "Azul vs cafe"
    dst_dir = ROOT / "audio" / "cafe_vs_azul"
    ensure_dirs([dst_dir])

    # (old NFC name, instrument, kind, note/chord, position)
    mapping = [
        ("Copia de Café a al aire.m4a", "cafe", "note", "a", "open"),
        ("Copia de Azul full a al aire.m4a", "azul", "note", "a", "open"),
        ("Copia de Café b al aire.m4a", "cafe", "note", "b", "open"),
        ("Copia de Azul full b al aire.m4a", "azul", "note", "b", "open"),
        ("Copia de Café c al aire.m4a", "cafe", "note", "c", "open"),
        ("Copia de Azul full c al aire.m4a", "azul", "note", "c", "open"),
        ("Copia de Café d al aire.m4a", "cafe", "note", "d", "open"),
        ("Copia de Azul full d al aire.m4a", "azul", "note", "d", "open"),
        ("Copia de Café e al aire.m4a", "cafe", "note", "e", "open"),
        ("Copia de Azul full e al aire.m4a", "azul", "note", "e", "open"),
        ("Copia de Café g al aire.m4a", "cafe", "note", "g", "open"),
        ("Copia de Azul full g al aire.m4a", "azul", "note", "g", "open"),
        ("Copia de Café a 12.m4a", "cafe", "note", "a", "fret_12"),
        ("Copia de Azul full a 12.m4a", "azul", "note", "a", "fret_12"),
        ("Copia de Café b 12.m4a", "cafe", "note", "b", "fret_12"),
        ("Copia de Azul full b 12.m4a", "azul", "note", "b", "fret_12"),
        ("Copia de Café c 12.m4a", "cafe", "note", "c", "fret_12"),
        ("Copia de Azul full c 12.m4a", "azul", "note", "c", "fret_12"),
        ("Copia de Café d 12.m4a", "cafe", "note", "d", "fret_12"),
        ("Copia de Azul full d 12.m4a", "azul", "note", "d", "fret_12"),
        ("Copia de Cafe e 12.m4a", "cafe", "note", "e", "fret_12"),  # missing accent in source
        ("Copia de Azul full e 12.m4a", "azul", "note", "e", "fret_12"),
        ("Copia de Café g 12.m4a", "cafe", "note", "g", "fret_12"),
        ("Copia de Azul full g 12.m4a", "azul", "note", "g", "fret_12"),
        ("Copia de Café 24 c.m4a", "cafe", "note", "c", "fret_24"),
        ("Copia de Azul full traste 24.m4a", "azul", "note", "c", "fret_24"),
        ("Copia de Café am7.m4a", "cafe", "chord", "am7", "na"),
        ("Copia de Azul full am7.m4a", "azul", "chord", "am7", "na"),
        ("Copia de Café cmaj7.m4a", "cafe", "chord", "cmaj7", "na"),
        ("Copia de Azul full Cmaj7.m4a", "azul", "chord", "cmaj7", "na"),
        ("Copia de Café cromática c 1 25.m4a", "cafe", "chromatic", "c", "frets_1_25"),
        ("Copia de Cromática 1 25 c azul full.m4a", "azul", "chromatic", "c", "frets_1_25"),
    ]

    by_name = {nfc(p.name): p for p in src_dir.glob("*.m4a")}
    rows = []
    rename_rows = []

    for old_name, instrument, kind, label, position in mapping:
        src = by_name.get(nfc(old_name))
        if src is None:
            raise FileNotFoundError(f"Missing cafe/azul source: {old_name}")

        if kind == "note":
            new_name = f"{instrument}__note_{label}__{position}.m4a"
            pair_id = f"note_{label}__{position}"
        elif kind == "chord":
            new_name = f"{instrument}__chord_{label}.m4a"
            pair_id = f"chord_{label}"
        else:
            new_name = f"{instrument}__chromatic_{label}__{position}.m4a"
            pair_id = f"chromatic_{label}__{position}"

        dst = dst_dir / new_name
        copy_file(src, dst)
        digest = sha256(dst)
        rows.append(
            {
                "pair_id": pair_id,
                "instrument": instrument,
                "kind": kind,
                "label": label,
                "position": position,
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "sha256": digest,
            }
        )
        rename_rows.append(
            {
                "module": "emulate_azul",
                "dataset": "cafe_vs_azul",
                "old_path": str(src.relative_to(ROOT)),
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "new_name": new_name,
                "sha256": digest,
            }
        )

    # pair-centric manifest
    pairs = {}
    for r in rows:
        pairs.setdefault(r["pair_id"], {"pair_id": r["pair_id"], "kind": r["kind"], "label": r["label"], "position": r["position"]})
        pairs[r["pair_id"]][f"{r['instrument']}_path"] = r["new_path"]
        pairs[r["pair_id"]][f"{r['instrument']}_sha256"] = r["sha256"]
        pairs[r["pair_id"]][f"{r['instrument']}_old_name"] = r["old_name"]

    pair_rows = list(pairs.values())
    write_csv(
        ROOT / "manifests" / "cafe_vs_azul_pairs.csv",
        pair_rows,
        [
            "pair_id",
            "kind",
            "label",
            "position",
            "cafe_path",
            "azul_path",
            "cafe_old_name",
            "azul_old_name",
            "cafe_sha256",
            "azul_sha256",
        ],
    )
    return rename_rows


def normalize_fine_tune() -> list[dict]:
    src_dir = ROOT / "Fine tunear rcs y mooer -20260730T192932Z-1-001" / "Fine tunear rcs y mooer"
    rc_dir = ROOT / "audio" / "rc_response"
    azul_dir = ROOT / "audio" / "azul_forced"
    ensure_dirs([rc_dir, azul_dir])

    rc_map = [
        ("Pink.m4a", "pink", "off", "none"),
        ("Pink rc bass on.m4a", "pink", "rc", "bass"),
        ("Pink rc hybrid on.m4a", "pink", "rc", "hybrid"),
        ("Pink rc guitar on.m4a", "pink", "rc", "guitar"),
        ("1 22k.m4a", "sweep_1_22k", "off", "none"),
        ("1 22k rc bass on.m4a", "sweep_1_22k", "rc", "bass"),
        ("1 22k rc hybrid on.m4a", "sweep_1_22k", "rc", "hybrid"),
        ("1 22k rc guitar on.m4a", "sweep_1_22k", "rc", "guitar"),
    ]
    azul_map = [
        ("Pink azul bass forced.m4a", "pink", "azul_forced", "bass"),
        ("Pink azul hybrid forced.m4a", "pink", "azul_forced", "hybrid"),
        ("Pink azul rc guitar forced.m4a", "pink", "azul_forced", "guitar"),  # source had extra "rc"
        ("1 22k azul bass forced.m4a", "sweep_1_22k", "azul_forced", "bass"),
        ("1 22k azul hybrid forced.m4a", "sweep_1_22k", "azul_forced", "hybrid"),
        ("1 22k azul guitar forced.m4a", "sweep_1_22k", "azul_forced", "guitar"),
    ]

    by_name = {nfc(p.name): p for p in src_dir.glob("*.m4a")}
    rename_rows = []
    rc_rows = []
    azul_rows = []

    for old_name, signal, mode, profile in rc_map:
        src = by_name[nfc(old_name)]
        if mode == "off":
            new_name = f"{signal}__off.m4a"
        else:
            new_name = f"{signal}__rc_{profile}.m4a"
        dst = rc_dir / new_name
        copy_file(src, dst)
        digest = sha256(dst)
        rc_rows.append(
            {
                "signal": signal,
                "mode": mode,
                "profile": profile,
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "sha256": digest,
            }
        )
        rename_rows.append(
            {
                "module": "rc_pedals",
                "dataset": "rc_response",
                "old_path": str(src.relative_to(ROOT)),
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "new_name": new_name,
                "sha256": digest,
            }
        )

    for old_name, signal, mode, profile in azul_map:
        src = by_name[nfc(old_name)]
        new_name = f"{signal}__azul_{profile}.m4a"
        dst = azul_dir / new_name
        copy_file(src, dst)
        digest = sha256(dst)
        azul_rows.append(
            {
                "signal": signal,
                "mode": mode,
                "profile": profile,
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "sha256": digest,
                "notes": "source filename had extra 'rc' token" if " rc " in old_name else "",
            }
        )
        rename_rows.append(
            {
                "module": "emulate_azul",
                "dataset": "azul_forced",
                "old_path": str(src.relative_to(ROOT)),
                "new_path": str(dst.relative_to(ROOT)),
                "old_name": old_name,
                "new_name": new_name,
                "sha256": digest,
            }
        )

    write_csv(
        ROOT / "manifests" / "rc_response_inventory.csv",
        rc_rows,
        ["signal", "mode", "profile", "new_path", "old_name", "sha256"],
    )
    write_csv(
        ROOT / "manifests" / "azul_forced_inventory.csv",
        azul_rows,
        ["signal", "mode", "profile", "new_path", "old_name", "sha256", "notes"],
    )
    return rename_rows


def move_tree_contents(src: Path, dst: Path, skip_names: set[str] | None = None) -> None:
    skip_names = skip_names or set()
    ensure_dirs([dst])
    for item in src.iterdir():
        if item.name in skip_names:
            continue
        if item.name.lower() in {"desktop.ini", "thumbs.db"}:
            continue
        if item.name == "__pycache__" or item.suffix == ".pyc":
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                move_tree_contents(item, target, skip_names)
            else:
                shutil.copytree(
                    item,
                    target,
                    ignore=shutil.ignore_patterns("desktop.ini", "Thumbs.db", "__pycache__", "*.pyc"),
                )
        else:
            copy_file(item, target)


def organize_emulate_azul() -> None:
    base = ROOT / "modules" / "emulate_azul"
    code = base / "code"
    results = base / "results"
    docs = base / "docs"
    ensure_dirs([code, results, docs])

    src = ROOT / "CAFE_AZUL_V10_2_ANALISIS_CODIGO (1)"
    move_tree_contents(src / "v10_2_code", code)
    move_tree_contents(src / "v10_2_results", results)

    # Keep the prompt as docs
    prompt = code / "PROMPT_MAESTRO_V10_2.md"
    if prompt.exists():
        shutil.move(str(prompt), str(docs / "PROMPT_MAESTRO_V10_2.md"))


def organize_rc_and_mooer() -> None:
    src = ROOT / "PEDAL_MOOER_MULTIZONE_MASTER_COMPLETO (1)" / "PEDAL_MOOER_MULTIZONE_MASTER"
    rc = ROOT / "modules" / "rc_pedals"
    mooer = ROOT / "modules" / "mooer_eq"
    ensure_dirs(
        [
            rc / "code",
            rc / "config",
            rc / "data",
            rc / "docs",
            rc / "checksums",
            mooer / "code",
            mooer / "config",
            mooer / "data",
            mooer / "docs",
        ]
    )

    # Code split
    rc_code = {
        "source_reconstruction_pipeline.py",
        "01_audio_reconstruction_and_384_audit.py",
        "requirements.txt",
    }
    mooer_code = {
        "02_multizone_discrete_optimization.py",
        "03_constraint_diagnostics.py",
        "04_operational_selection.py",
        "05_comparison_by_region.py",
        "requirements.txt",
    }
    for name in rc_code:
        p = src / "code" / name
        if p.exists():
            copy_file(p, rc / "code" / name)
    for name in mooer_code:
        p = src / "code" / name
        if p.exists():
            copy_file(p, mooer / "code" / name)

    # Config: shared technical config goes to both; analysis config to mooer
    if (src / "config" / "config.json").exists():
        copy_file(src / "config" / "config.json", rc / "config" / "config.json")
        copy_file(src / "config" / "config.json", mooer / "config" / "config.json")
    if (src / "config" / "analysis_config.json").exists():
        copy_file(src / "config" / "analysis_config.json", mooer / "config" / "analysis_config.json")

    rc_data_prefixes = (
        "audio_qc",
        "refined_curves",
        "method_validation",
        "sweep_",
        "pink_",
        "grid_convergence",
        "nonlinearity",
        "smoothing_validation",
        "target_uncertainty",
    )
    mooer_data_exact = {
        "PRESETS_RECOMENDADOS.json",
        "results_summary.json",
        "final_presets.csv",
        "final_preset_selection_metrics.csv",
        "final_metrics_by_region.csv",
        "final_curves_and_residuals.csv",
        "optimization_candidates_all.csv",
        "pareto_candidates.csv",
        "monte_carlo_candidates.csv",
        "constraint_decomposition.csv",
        "historical_comparison_same_metrics.csv",
        "historical_metrics_by_region.csv",
        "improvement_vs_measurement_uncertainty.csv",
        "sensitivity_plus_minus_0_5db.csv",
        "ideal_vs_calibrated_model.csv",
        "balanced_band_contributions.csv",
        "error_by_octave.csv",
        "cross_validation.csv",
        "global_gain_free_diagnostic.csv",
    }

    for p in (src / "data").glob("*"):
        if p.name.lower() == "desktop.ini":
            continue
        if p.name in mooer_data_exact or p.name.startswith(
            (
                "final_",
                "optimization_",
                "pareto_",
                "monte_carlo_",
                "constraint_",
                "historical_",
                "improvement_",
                "sensitivity_",
                "ideal_vs_",
                "balanced_",
                "error_by_",
                "cross_validation",
                "global_gain_",
                "PRESETS_",
                "results_summary",
            )
        ):
            copy_file(p, mooer / "data" / p.name)
        elif p.name.startswith(rc_data_prefixes):
            copy_file(p, rc / "data" / p.name)
        else:
            # shared / ambiguous → keep in both for now
            copy_file(p, rc / "data" / p.name)
            copy_file(p, mooer / "data" / p.name)

    # Docs split
    rc_docs = {
        "01_PIPELINE_DSP_COMPLETO.md",
        "02_CALIDAD_Y_DESCRIPCION_DE_AUDIOS.md",
        "07_REPRODUCIBILIDAD_Y_TRAZABILIDAD.md",
    }
    mooer_docs = {
        "00_RESUMEN_EJECUTIVO.md",
        "03_INFORME_TECNICO_FINAL.md",
        "04_OPTIMIZACION_PARETO.md",
        "05_INCERTIDUMBRE_Y_VALIDACION.md",
        "06_COMPARACION_PRESETS_ANTERIORES.md",
        "07_REPRODUCIBILIDAD_Y_TRAZABILIDAD.md",
        "ESPECIFICACION_USUARIO.txt",
    }
    for name in rc_docs:
        p = src / "docs" / name
        if p.exists():
            copy_file(p, rc / "docs" / name)
    for name in mooer_docs:
        p = src / "docs" / name
        if p.exists():
            copy_file(p, mooer / "docs" / name)

    # Checksums belong with RC audio provenance
    if (src / "checksums").exists():
        move_tree_contents(src / "checksums", rc / "checksums")

    # Excel results workbook + legacy package manifest
    xlsx = src / "PEDAL_MOOER_MULTIZONE_RESULTADOS.xlsx"
    if xlsx.exists():
        copy_file(xlsx, mooer / "data" / "PEDAL_MOOER_MULTIZONE_RESULTADOS.xlsx")
    manifest = src / "PACKAGE_MANIFEST.md"
    if manifest.exists():
        copy_file(manifest, mooer / "docs" / "PACKAGE_MANIFEST_LEGACY.md")


def remove_old_roots() -> None:
    old = [
        ROOT / "Azul vs cafe-20260730T193323Z-1-001",
        ROOT / "CAFE_AZUL_V10_2_ANALISIS_CODIGO (1)",
        ROOT / "Fine tunear rcs y mooer -20260730T192932Z-1-001",
        ROOT / "PEDAL_MOOER_MULTIZONE_MASTER_COMPLETO (1)",
    ]
    for path in old:
        if path.exists():
            shutil.rmtree(path)


def main() -> None:
    ensure_dirs(
        [
            ROOT / "audio" / "cafe_vs_azul",
            ROOT / "audio" / "rc_response",
            ROOT / "audio" / "azul_forced",
            ROOT / "manifests",
            ROOT / "modules" / "emulate_azul",
            ROOT / "modules" / "rc_pedals",
            ROOT / "modules" / "mooer_eq",
            ROOT / "scripts",
        ]
    )

    rename_rows = []
    rename_rows.extend(normalize_cafe_azul())
    rename_rows.extend(normalize_fine_tune())
    write_csv(
        ROOT / "manifests" / "rename_map.csv",
        rename_rows,
        ["module", "dataset", "old_path", "new_path", "old_name", "new_name", "sha256"],
    )

    organize_emulate_azul()
    organize_rc_and_mooer()
    remove_old_roots()

    print("Reorganization complete.")
    print(f"Audio cafe_vs_azul: {len(list((ROOT / 'audio' / 'cafe_vs_azul').glob('*.m4a')))}")
    print(f"Audio rc_response: {len(list((ROOT / 'audio' / 'rc_response').glob('*.m4a')))}")
    print(f"Audio azul_forced: {len(list((ROOT / 'audio' / 'azul_forced').glob('*.m4a')))}")


if __name__ == "__main__":
    main()
