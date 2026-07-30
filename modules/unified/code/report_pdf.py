"""Generate orchestrated PDF report: Café→Azul → RC → 3 Mooer presets (min error)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from bridge import load_azul, load_rc
from mooer_fit import _load_mooer_model, fit_mooer_anti_error, save_fit
from paths import RepoPaths, discover_repo
from targets import rc_target

# GE300 hard constraints for this report
FREQS = (30.0, 148.0, 735.0, 3637.0, 18000.0)
Q_DISPLAY = 0.3
GLOBAL_GAIN = 3.0
LOCK_18K_DB = -16.0
LOCKED = {4: LOCK_18K_DB}  # band index 4 = 18000 Hz

SETUP_LABELS = {
    "bass": "Bajo",
    "hybrid": "Híbrido",
    "guitar": "Guitarra",
}


def _style():
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.facecolor": "white",
            "axes.facecolor": "#fafafa",
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    )


def _page_text(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))  # A4 landscape
    fig.text(0.06, 0.92, title, fontsize=18, fontweight="bold", va="top")
    y = 0.84
    for line in lines:
        fig.text(0.06, y, line, fontsize=11, va="top", family="DejaVu Sans")
        y -= 0.045
        if y < 0.06:
            break
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_azul(pdf: PdfPages, paths: RepoPaths) -> dict:
    azul = load_azul(paths)
    curve = azul.load_curve()
    gain = float(azul.load_gain().iloc[0]["gain_recommended_db"])
    f = curve.frequency_hz
    central = curve.central_db
    robust = curve.robust_db
    safe = curve.safe_db
    total = curve.total_central_with_gain_db
    if total is None:
        total = central + gain

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle("1. Transferencia Café → Azul (V10.2)", fontsize=14, fontweight="bold")

    ax = axes[0, 0]
    ax.semilogx(f, central, label="Central (timbre)", lw=1.8)
    ax.semilogx(f, robust, label="Robust", lw=1.2, alpha=0.85)
    ax.semilogx(f, safe, label="Safe", lw=1.2, alpha=0.85)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 20000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Curvas de timbre")
    ax.legend(loc="best", fontsize=8)

    ax = axes[0, 1]
    ax.semilogx(f, total, color="#c45c26", lw=1.8, label=f"Total (+ gain {gain:+.2f} dB)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 20000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Curva total con gain global")
    ax.legend(loc="best", fontsize=8)

    ax = axes[1, 0]
    m = f <= 120
    ax.plot(f[m], central[m], label="Central")
    ax.plot(f[m], robust[m], label="Robust")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Zoom 20–120 Hz")
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    m = (f >= 800) & (f <= 12000)
    ax.semilogx(f[m], central[m], label="Central")
    ax.semilogx(f[m], robust[m], label="Robust")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Zoom 0.8–12 kHz")
    ax.legend(fontsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig)
    plt.close(fig)

    return {
        "gain_recommended_db": gain,
        "curve_min_db": float(np.min(central)),
        "curve_max_db": float(np.max(central)),
    }


def _plot_rc(pdf: PdfPages, paths: RepoPaths) -> dict:
    rc = load_rc(paths)
    curves = rc.load_refined_curves()
    f = curves.frequency_hz

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle("2. Respuestas RC (pink+sweep fusionadas)", fontsize=14, fontweight="bold")

    ax = axes[0, 0]
    for key, label in SETUP_LABELS.items():
        ax.semilogx(f, curves.setup_db(key), label=label, lw=1.6)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 20000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Curvas recomendadas (analógicas)")
    ax.legend(fontsize=8)

    for ax, key, title in (
        (axes[0, 1], "bass", "Bajo — detalle"),
        (axes[1, 0], "hybrid", "Híbrido — detalle"),
        (axes[1, 1], "guitar", "Guitarra — detalle"),
    ):
        y = curves.setup_db(key)
        u = curves.uncertainties[key]
        ax.semilogx(f, y, lw=1.6, label="recomendado")
        ax.fill_between(f, y - u, y + u, alpha=0.25, label="± incertidumbre")
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlim(20, 20000)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title(title)
        ax.legend(fontsize=7)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig)
    plt.close(fig)

    summary = {}
    for key in SETUP_LABELS:
        y = curves.setup_db(key)
        summary[key] = {
            "min_db": float(np.min(y)),
            "max_db": float(np.max(y)),
            "at_30hz_db": float(np.interp(30, f, y)),
        }
    return summary


def _fit_three_presets(
    paths: RepoPaths,
    *,
    de_seeds: int,
    random_starts: int,
    seed: int,
) -> dict[str, dict]:
    mm = _load_mooer_model()
    out_dir = paths.unified / "data" / "fits" / "report_locked18k"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for setup, label in SETUP_LABELS.items():
        target = rc_target(rc_setup=setup, paths=paths)
        fit = fit_mooer_anti_error(
            target,
            de_seeds=de_seeds,
            random_starts=random_starts,
            seed=seed,
            locked_gains_db=LOCKED,
        )
        # Force name to Spanish preset label for artifacts
        fit.target_name = f"mooer_{setup}_locked18k"
        written = save_fit(fit, target, out_dir)
        y = mm.preset_response_db(target.frequency_hz, fit.gains_display_db, mm.DEFAULT_MODEL)
        results[setup] = {
            "label": label,
            "fit": fit,
            "target": target,
            "mooer_db": y,
            "written": {k: str(v) for k, v in written.items()},
        }
        assert abs(fit.gains_display_db[4] - LOCK_18K_DB) < 1e-9, "18 kHz lock failed"
    return results


def _plot_presets_overview(pdf: PdfPages, results: dict[str, dict]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(
        "3. Presets Mooer GE300 — mínimo error anti-error\n"
        f"Q={Q_DISPLAY} · f=[{', '.join(str(int(x)) for x in FREQS)}] · "
        f"global=+{GLOBAL_GAIN:.0f} dB · 18000 Hz={LOCK_18K_DB:.0f} dB (lock)",
        fontsize=13,
        fontweight="bold",
    )

    ax = fig.add_axes([0.06, 0.42, 0.88, 0.42])
    # Table
    cols = ["Preset", "30 Hz", "148 Hz", "735 Hz", "3637 Hz", "18000 Hz", "Score", "Worst", "Global"]
    cell = []
    for setup in ("bass", "hybrid", "guitar"):
        r = results[setup]
        g = r["fit"].gains_display_db
        m = r["fit"].metrics
        cell.append(
            [
                r["label"],
                f"{g[0]:+.1f}",
                f"{g[1]:+.1f}",
                f"{g[2]:+.1f}",
                f"{g[3]:+.1f}",
                f"{g[4]:+.1f}",
                f"{r['fit'].score:.3f}",
                f"{m['worst']:.3f}",
                f"{m['global']:.3f}",
            ]
        )
    ax.axis("off")
    table = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.6)
    for (row, col), cell_obj in table.get_celld().items():
        if row == 0:
            cell_obj.set_facecolor("#2f4f4f")
            cell_obj.set_text_props(color="white", fontweight="bold")
        elif col == 5:  # locked 18k
            cell_obj.set_facecolor("#ffe8d6")

    ax2 = fig.add_axes([0.08, 0.08, 0.84, 0.28])
    x = np.arange(5)
    width = 0.25
    for i, setup in enumerate(("bass", "hybrid", "guitar")):
        g = results[setup]["fit"].gains_display_db
        ax2.bar(x + (i - 1) * width, g, width, label=results[setup]["label"])
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{int(f)} Hz" for f in FREQS])
    ax2.axhline(0, color="k", lw=0.6)
    ax2.axhline(LOCK_18K_DB, color="r", ls="--", lw=0.8, label="lock 18 kHz")
    ax2.set_ylabel("Gain display (dB)")
    ax2.set_title("Ganancias por banda")
    ax2.legend(fontsize=8, ncol=4)
    pdf.savefig(fig)
    plt.close(fig)


def _plot_each_preset(pdf: PdfPages, results: dict[str, dict]) -> None:
    for setup in ("bass", "hybrid", "guitar"):
        r = results[setup]
        t = r["target"]
        f = t.frequency_hz
        target = t.target_db
        mooer = r["mooer_db"]
        err = mooer - target
        g = r["fit"].gains_display_db

        fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
        fig.suptitle(
            f"Preset {r['label']} — target RC vs Mooer (score={r['fit'].score:.3f})",
            fontsize=13,
            fontweight="bold",
        )

        ax = axes[0, 0]
        ax.semilogx(f, target, label="RC target", lw=1.8)
        ax.semilogx(f, mooer, label="Mooer GE300", lw=1.5, ls="--")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 20000)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Curva completa")
        ax.legend(fontsize=8)

        ax = axes[0, 1]
        ax.semilogx(f, err, color="#a33", lw=1.4)
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 15500)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Error (Mooer − target)")

        ax = axes[1, 0]
        m = f <= 250
        ax.plot(f[m], target[m], label="RC")
        ax.plot(f[m], mooer[m], label="Mooer", ls="--")
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Zoom graves ≤250 Hz")
        ax.legend(fontsize=8)

        ax = axes[1, 1]
        ax.axis("off")
        metrics = r["fit"].metrics
        lines = [
            f"Gains display: {g}",
            f"Freqs: {list(FREQS)}",
            f"Q display: {Q_DISPLAY} (lock)",
            f"Global: +{GLOBAL_GAIN:.0f} dB (lock)",
            f"18000 Hz: {g[4]:+.1f} dB (lock)",
            "",
            f"Anti-error score: {r['fit'].score:.4f}",
            f"Worst regional RMSE: {metrics['worst']:.4f} dB",
            f"Avg regional RMSE: {metrics['avg']:.4f} dB",
            f"Global RMSE: {metrics['global']:.4f} dB",
            "",
            "RMSE por región:",
        ]
        for name in ("Subgraves", "Graves", "Medios", "Presencia", "Brillo"):
            if name in metrics:
                lines.append(f"  {name}: {metrics[name]:.4f} dB")
        ax.text(0.02, 0.98, "\n".join(lines), va="top", family="DejaVu Sans", fontsize=9)

        fig.tight_layout(rect=[0, 0, 1, 0.95])
        pdf.savefig(fig)
        plt.close(fig)


def _write_presets_json(paths: RepoPaths, results: dict[str, dict]) -> Path:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "unified orchestrator report",
        "constraints": {
            "frequencies_hz": list(FREQS),
            "q_display": Q_DISPLAY,
            "global_gain_db": GLOBAL_GAIN,
            "band_18000_locked_db": LOCK_18K_DB,
            "objective": "anti_error_minimax_balanced",
        },
        "presets": {},
    }
    for setup in ("bass", "hybrid", "guitar"):
        r = results[setup]
        payload["presets"][r["label"]] = {
            "rc_setup": setup,
            "gains_display_db": r["fit"].gains_display_db,
            "q_display": [Q_DISPLAY] * 5,
            "global_gain_db": GLOBAL_GAIN,
            "anti_error_score": r["fit"].score,
            "metrics": {
                k: r["fit"].metrics[k]
                for k in (
                    "worst",
                    "avg",
                    "global",
                    "Subgraves",
                    "Graves",
                    "Medios",
                    "Presencia",
                    "Brillo",
                )
                if k in r["fit"].metrics
            },
        }
    out = paths.unified / "data" / "ORCHESTRATED_PRESETS_LOCKED18K.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also mirror into mooer_eq for operational use
    mooer_out = paths.mooer_eq / "data" / "PRESETS_ORQUESTADOR_LOCKED18K.json"
    mooer_payload = {
        "global_gain_db": GLOBAL_GAIN,
        "frequencies_hz": list(FREQS),
        "q_display": [Q_DISPLAY] * 5,
        "band_18000_locked_db": LOCK_18K_DB,
        "presets": {
            label: {
                "gains_display_db": payload["presets"][label]["gains_display_db"],
                "anti_error_score": payload["presets"][label]["anti_error_score"],
                "reason": (
                    "Optimizado por unified (anti-error) con Q=0.3, "
                    "freqs locked y 18000 Hz = -16 dB."
                ),
            }
            for label in ("Bajo", "Híbrido", "Guitarra")
        },
    }
    mooer_out.write_text(json.dumps(mooer_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def generate_report(
    output_pdf: str | Path | None = None,
    *,
    de_seeds: int = 6,
    random_starts: int = 600,
    seed: int = 20260730,
    paths: RepoPaths | None = None,
) -> dict:
    """Fit 3 RC→Mooer presets (18k locked) and write the ordered PDF at repo root."""
    _style()
    paths = paths or discover_repo()
    if output_pdf is None:
        output_pdf = paths.repo / "INFORME_ORQUESTADOR_AZUL_RC_MOOER.pdf"
    output_pdf = Path(output_pdf)

    results = _fit_three_presets(
        paths, de_seeds=de_seeds, random_starts=random_starts, seed=seed
    )
    presets_json = _write_presets_json(paths, results)

    with PdfPages(output_pdf) as pdf:
        _page_text(
            pdf,
            "Informe orquestador — Azul · RC · Mooer GE300",
            [
                f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                "Orden del informe:",
                "  1) Transferencia Café → Azul (curvas V10.2)",
                "  2) Respuestas de pedales RC (Bajo / Híbrido / Guitarra)",
                "  3) Tres presets Mooer GE300 de mínimo error",
                "",
                "Constraints GE300 (hard):",
                f"  · Frecuencias locked: {', '.join(str(int(x)) for x in FREQS)} Hz",
                f"  · Q display locked: {Q_DISPLAY}",
                f"  · Global gain locked: +{GLOBAL_GAIN:.0f} dB",
                f"  · Banda 18000 Hz locked: {LOCK_18K_DB:.0f} dB",
                "  · Gains display: −16 … +16 dB, step 0.5",
                "",
                "Objetivo: anti-error (worst regional RMSE + penalties).",
                "Los presets se optimizan desde las curvas RC medidas (no histórico fijo).",
            ],
        )
        azul_sum = _plot_azul(pdf, paths)
        rc_sum = _plot_rc(pdf, paths)
        _plot_presets_overview(pdf, results)
        _plot_each_preset(pdf, results)

        # Closing summary page
        lines = [
            "Resumen ejecutivo de presets (gains display dB):",
            "",
        ]
        for setup in ("bass", "hybrid", "guitar"):
            r = results[setup]
            g = r["fit"].gains_display_db
            lines.append(
                f"  {r['label']}: [{g[0]:+.1f}, {g[1]:+.1f}, {g[2]:+.1f}, {g[3]:+.1f}, {g[4]:+.1f}]  "
                f"score={r['fit'].score:.3f}"
            )
        lines += [
            "",
            f"Azul gain global recomendado: {azul_sum['gain_recommended_db']:+.2f} dB",
            f"Artefactos JSON: {presets_json}",
            f"PDF: {output_pdf}",
        ]
        _page_text(pdf, "4. Cierre — presets listos para GE300", lines)

        d = pdf.infodict()
        d["Title"] = "Informe orquestador Azul RC Mooer"
        d["Author"] = "unified orchestrator"
        d["Subject"] = "Café→Azul, RC curves, Mooer presets locked 18k=-16"

    summary = {
        "pdf": str(output_pdf),
        "presets_json": str(presets_json),
        "azul": azul_sum,
        "rc": rc_sum,
        "presets": {
            results[s]["label"]: {
                "gains_display_db": results[s]["fit"].gains_display_db,
                "score": results[s]["fit"].score,
                "worst": results[s]["fit"].metrics["worst"],
                "global": results[s]["fit"].metrics["global"],
            }
            for s in ("bass", "hybrid", "guitar")
        },
        "constraints": {
            "frequencies_hz": list(FREQS),
            "q_display": Q_DISPLAY,
            "global_gain_db": GLOBAL_GAIN,
            "band_18000_locked_db": LOCK_18K_DB,
        },
    }
    summary_path = paths.unified / "data" / "informe_orquestador_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    return summary
