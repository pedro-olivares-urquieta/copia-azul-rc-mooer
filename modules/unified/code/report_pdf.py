"""PDF orquestado: Café→Azul + RC → 3 presets Mooer = Azul(+gain)+RC mezclados."""
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
from targets import azul_rc_target, azul_target

# GE300 hard constraints
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
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.text(0.06, 0.92, title, fontsize=18, fontweight="bold", va="top")
    y = 0.84
    for line in lines:
        fig.text(0.06, y, line, fontsize=11, va="top", family="DejaVu Sans")
        y -= 0.042
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
    ax.set_title("Curva total con gain global (entra al preset)")
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
    fig.suptitle("2. Respuestas RC (se mezclan con Azul en el preset)", fontsize=14, fontweight="bold")

    ax = axes[0, 0]
    for key, label in SETUP_LABELS.items():
        ax.semilogx(f, curves.setup_db(key), label=label, lw=1.6)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 20000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Curvas RC recomendadas")
    ax.legend(fontsize=8)

    for ax, key, title in (
        (axes[0, 1], "bass", "Bajo"),
        (axes[1, 0], "hybrid", "Híbrido"),
        (axes[1, 1], "guitar", "Guitarra"),
    ):
        y = curves.setup_db(key)
        u = curves.uncertainties[key]
        ax.semilogx(f, y, lw=1.6, label="RC")
        ax.fill_between(f, y - u, y + u, alpha=0.25, label="± unc")
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


def _plot_composition(pdf: PdfPages, paths: RepoPaths, azul_gain: float) -> None:
    """Show Azul + RC = target compuesto (lo que el Mooer debe emular)."""
    azul = azul_target(variant="central", include_gain=True, paths=paths)
    rc = load_rc(paths)
    curves = rc.load_refined_curves()
    f = curves.frequency_hz
    azul_y = np.interp(np.log(f), np.log(azul.frequency_hz), azul.target_db)

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle(
        f"2b. Mezcla Azul(+gain {azul_gain:+.2f} dB) + RC  →  target del preset Mooer",
        fontsize=13,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ax.semilogx(f, azul_y, label="Azul (+gain)", lw=1.8, color="#c45c26")
    for key, label in SETUP_LABELS.items():
        ax.semilogx(f, curves.setup_db(key), label=f"RC {label}", lw=1.2, alpha=0.85)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlim(20, 20000)
    ax.set_title("Componentes por separado")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=7)

    for ax, key, label in (
        (axes[0, 1], "bass", "Bajo"),
        (axes[1, 0], "hybrid", "Híbrido"),
        (axes[1, 1], "guitar", "Guitarra"),
    ):
        rc_y = curves.setup_db(key)
        mixed = azul_y + rc_y
        ax.semilogx(f, azul_y, label="Azul", lw=1.2, alpha=0.7)
        ax.semilogx(f, rc_y, label="RC", lw=1.2, alpha=0.7)
        ax.semilogx(f, mixed, label="Azul+RC (target)", lw=2.0, color="#1b6ca8")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 20000)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title(f"Target compuesto → preset {label}")
        ax.legend(fontsize=7)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)


def _fit_three_presets(
    paths: RepoPaths,
    *,
    de_seeds: int,
    random_starts: int,
    seed: int,
) -> dict[str, dict]:
    """Fit Mooer to Azul(+gain)+RC for each setup — one mixed preset each."""
    mm = _load_mooer_model()
    out_dir = paths.unified / "data" / "fits" / "report_azul_plus_rc_locked18k"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for setup, label in SETUP_LABELS.items():
        # KEY: composed target = Azul (with gain) + RC  → single Mooer preset
        target = azul_rc_target(
            rc_setup=setup,
            compose="plus",
            azul_variant="central",
            include_gain=True,
            paths=paths,
        )
        fit = fit_mooer_anti_error(
            target,
            de_seeds=de_seeds,
            random_starts=random_starts,
            seed=seed,
            locked_gains_db=LOCKED,
        )
        fit.target_name = f"azul_plus_rc_{setup}_locked18k"
        written = save_fit(fit, target, out_dir)
        y = mm.preset_response_db(target.frequency_hz, fit.gains_display_db, mm.DEFAULT_MODEL)
        results[setup] = {
            "label": f"Azul+RC {label}",
            "short_label": label,
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
        "3. Presets Mooer = Azul(+gain) + RC  (mínimo error)\n"
        f"Q={Q_DISPLAY} · f=[{', '.join(str(int(x)) for x in FREQS)}] · "
        f"global=+{GLOBAL_GAIN:.0f} dB · 18000 Hz={LOCK_18K_DB:.0f} dB (lock)",
        fontsize=12,
        fontweight="bold",
    )

    ax = fig.add_axes([0.04, 0.42, 0.92, 0.42])
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
    table.set_fontsize(8.5)
    table.scale(1.0, 1.6)
    for (row, col), cell_obj in table.get_celld().items():
        if row == 0:
            cell_obj.set_facecolor("#2f4f4f")
            cell_obj.set_text_props(color="white", fontweight="bold")
        elif col == 5:
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
    ax2.set_title("Ganancias por banda (un solo preset emula Azul+RC)")
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
        azul_gain = float(t.meta.get("gain_db", 0.0))

        fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
        fig.suptitle(
            f"Preset {r['label']} — target Azul(+gain)+RC vs Mooer  "
            f"(score={r['fit'].score:.3f}, Azul gain={azul_gain:+.2f} dB)",
            fontsize=12,
            fontweight="bold",
        )

        ax = axes[0, 0]
        ax.semilogx(f, target, label="Target Azul+RC", lw=1.8)
        ax.semilogx(f, mooer, label="Mooer GE300", lw=1.5, ls="--")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 20000)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Curva completa (mezcla)")
        ax.legend(fontsize=8)

        ax = axes[0, 1]
        ax.semilogx(f, err, color="#a33", lw=1.4)
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 15500)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Error (Mooer − Azul−RC)")

        ax = axes[1, 0]
        m = f <= 250
        ax.plot(f[m], target[m], label="Azul+RC")
        ax.plot(f[m], mooer[m], label="Mooer", ls="--")
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.set_title("Zoom graves ≤250 Hz")
        ax.legend(fontsize=8)

        ax = axes[1, 1]
        ax.axis("off")
        metrics = r["fit"].metrics
        lines = [
            "Target = Azul(central + gain) + RC",
            f"RC setup: {setup}",
            f"Azul gain incluido: {azul_gain:+.2f} dB",
            "",
            f"Gains display: {g}",
            f"Freqs locked: {list(FREQS)}",
            f"Q display: {Q_DISPLAY} (lock)",
            f"Global: +{GLOBAL_GAIN:.0f} dB (lock)",
            f"18000 Hz: {g[4]:+.1f} dB (lock)",
            "",
            f"Anti-error score: {r['fit'].score:.4f}",
            f"Worst RMSE: {metrics['worst']:.4f} dB",
            f"Avg RMSE: {metrics['avg']:.4f} dB",
            f"Global RMSE: {metrics['global']:.4f} dB",
            "",
            "RMSE por región:",
        ]
        for name in ("Subgraves", "Graves", "Medios", "Presencia", "Brillo"):
            if name in metrics:
                lines.append(f"  {name}: {metrics[name]:.4f} dB")
        ax.text(0.02, 0.98, "\n".join(lines), va="top", family="DejaVu Sans", fontsize=9)

        fig.tight_layout(rect=[0, 0, 1, 0.94])
        pdf.savefig(fig)
        plt.close(fig)


def _write_presets_json(paths: RepoPaths, results: dict[str, dict]) -> Path:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "unified orchestrator — Azul(+gain)+RC mixed into one Mooer preset",
        "formula": "target_db = azul_central_db + azul_gain_db + rc_setup_db",
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
        label = r["short_label"]
        payload["presets"][label] = {
            "display_name": r["label"],
            "rc_setup": setup,
            "compose": "azul_plus_rc",
            "include_azul_gain": True,
            "azul_gain_db": float(r["target"].meta.get("gain_db", 0.0)),
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
    out = paths.unified / "data" / "ORCHESTRATED_PRESETS_AZUL_PLUS_RC_LOCKED18K.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Mirror operational JSON
    mooer_out = paths.mooer_eq / "data" / "PRESETS_ORQUESTADOR_AZUL_PLUS_RC_LOCKED18K.json"
    mooer_payload = {
        "global_gain_db": GLOBAL_GAIN,
        "frequencies_hz": list(FREQS),
        "q_display": [Q_DISPLAY] * 5,
        "band_18000_locked_db": LOCK_18K_DB,
        "formula": "Azul(central+gain) + RC → one GE300 preset",
        "presets": {
            label: {
                "gains_display_db": payload["presets"][label]["gains_display_db"],
                "anti_error_score": payload["presets"][label]["anti_error_score"],
                "azul_gain_db": payload["presets"][label]["azul_gain_db"],
                "reason": (
                    "Un solo preset GE300 emula Azul(+gain) + RC. "
                    "Q=0.3, freqs locked, 18000 Hz=-16 dB, global=+3 dB."
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
    """Fit 3 mixed Azul(+gain)+RC → Mooer presets and write ordered PDF at repo root."""
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
            "Informe orquestador — Azul + RC → preset Mooer único",
            [
                f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                "",
                "Idea clave: NO son dos EQs aparte.",
                "Cada preset Mooer emula la MEZCLA:",
                "    target = Azul(central) + gain_Azul + RC(setup)",
                "Así el RC 'nuevo' ya lleva el Azul (y su ganancia) adentro.",
                "",
                "Orden del informe:",
                "  1) Transferencia Café → Azul (curvas + gain)",
                "  2) Respuestas RC Bajo / Híbrido / Guitarra",
                "  2b) Mezcla Azul(+gain)+RC = target compuesto",
                "  3) Tres presets Mooer GE300 de mínimo error sobre esa mezcla",
                "",
                "Constraints GE300 (hard):",
                f"  · Frecuencias locked: {', '.join(str(int(x)) for x in FREQS)} Hz",
                f"  · Q display locked: {Q_DISPLAY}",
                f"  · Global gain locked: +{GLOBAL_GAIN:.0f} dB",
                f"  · Banda 18000 Hz locked: {LOCK_18K_DB:.0f} dB",
                "  · Gains display: −16 … +16 dB, step 0.5",
            ],
        )
        azul_sum = _plot_azul(pdf, paths)
        rc_sum = _plot_rc(pdf, paths)
        _plot_composition(pdf, paths, azul_sum["gain_recommended_db"])
        _plot_presets_overview(pdf, results)
        _plot_each_preset(pdf, results)

        lines = [
            "Cada preset = un GE300 que lleva Azul(+gain) + RC juntos:",
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
            f"Azul gain incluido en el target: {azul_sum['gain_recommended_db']:+.2f} dB",
            f"JSON: {presets_json}",
            f"PDF: {output_pdf}",
        ]
        _page_text(pdf, "4. Cierre — presets Azul+RC listos para GE300", lines)

        d = pdf.infodict()
        d["Title"] = "Informe orquestador Azul+RC → Mooer"
        d["Author"] = "unified orchestrator"
        d["Subject"] = "Mixed Azul(+gain)+RC presets, 18k=-16, Q=0.3"

    summary = {
        "pdf": str(output_pdf),
        "presets_json": str(presets_json),
        "formula": "target = azul_central + azul_gain + rc_setup",
        "azul": azul_sum,
        "rc": rc_sum,
        "presets": {
            results[s]["short_label"]: {
                "display_name": results[s]["label"],
                "gains_display_db": results[s]["fit"].gains_display_db,
                "score": results[s]["fit"].score,
                "worst": results[s]["fit"].metrics["worst"],
                "global": results[s]["fit"].metrics["global"],
                "azul_gain_db": float(results[s]["target"].meta.get("gain_db", 0.0)),
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
