"""PDF de repasada Café→Azul: espectros Café/Azul + todas las curvas EQ + operativa fiel."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from scipy import signal as _sig

from bridge import load_rc
from paths import RepoPaths, discover_repo

SETUP_LABELS = {
    "bass": "Bajo",
    "hybrid": "Híbrido",
    "guitar": "Guitarra",
}


def _emulate_code(paths: RepoPaths) -> Path:
    return paths.emulate_azul / "code"


def _load_build(paths: RepoPaths):
    code = str(_emulate_code(paths).resolve())
    if code not in sys.path:
        sys.path.insert(0, code)
    import build_v10_2 as m  # noqa: WPS433
    import improve_v15 as v15  # noqa: WPS433

    return m, v15


def _results_dir(paths: RepoPaths) -> Path:
    det = paths.emulate_azul / "_runs" / "det_A" / "results"
    if (det / "CURVA_COPIA_OPERATIVA.csv").exists():
        return det
    return paths.emulate_azul / "results"


def _style() -> None:
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
    fig.text(0.06, 0.94, title, fontsize=16, fontweight="bold", va="top")
    y = 0.88
    for line in lines:
        size = 10 if len(line) < 110 else 9
        fig.text(0.06, y, line, fontsize=size, va="top", family="DejaVu Sans")
        y -= 0.034
        if y < 0.05:
            break
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _interp(f_src, y_src, f_dst):
    return np.interp(np.log(f_dst), np.log(f_src), y_src)


def _read_curve(path: Path, col: str) -> tuple[np.ndarray, np.ndarray] | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if col not in df.columns:
        return None
    return df["frequency_hz"].to_numpy(float), df[col].to_numpy(float)


def _spectrum_db(y: np.ndarray, sr: int, nperseg: int = 8192):
    y = y - np.mean(y)
    n = max(int(0.02 * sr), 1)
    fr = y[: len(y) // n * n].reshape(-1, n)
    e = np.sqrt(np.mean(fr**2, axis=1))
    act = fr[e > 0.2 * e.max()].ravel() if e.max() > 0 else y
    f, P = _sig.welch(act, sr, nperseg=min(nperseg, max(256, len(act) // 4)))
    return f, 10 * np.log10(np.maximum(P, 1e-30))


def _cover(pdf: PdfPages, out: Path, gain: float, variant: str, hold: float | None) -> None:
    hold_s = f"{hold:.3f} dB" if hold is not None and np.isfinite(hold) else "n/d"
    _page_text(
        pdf,
        "Informe Café → Azul — copia fiel (sin suavizar)",
        [
            f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"PDF: {out.name}",
            "",
            "Repasada general (evidencia = 16 parejas AAC / 32 M4A):",
            "  · Separación nivel vs timbre: gain ≈ −12 dB (consenso V12/V15/V17/V4.1)",
            f"  · EQ operativa: {variant}",
            f"  · Gain operativa: {gain:+.3f} dB",
            f"  · Hold-out crítico 0.5–8 kHz: {hold_s}",
            "  · Sin suavizado regional ni contracción EQ×reliability",
            "",
            "Qué hacemos mejor que V4.1: DPSS, F0 refine, matching acústico,",
            "offsets estimados, repro bit-idéntica, métrica render Café+EQ vs Azul.",
            "",
            "Qué adoptamos de V4.1 para fidelidad: pesos SNR/ciclos/AAC, pair-first,",
            "confianza de alineación, repetibilidad de fase, neutralidad energética.",
            "",
            "Qué NO adoptamos como EQ principal: smooth held-out, EQ×fiabilidad,",
            "multiplicadores físicos fijos 0.62/0.55/0.85.",
            "",
            "Contenido:",
            "  1) Espectros Café vs Azul (pares representativos)",
            "  2) EQ operativa + total con gain",
            "  3) Todas las curvas de transferencia (V10.2…V17)",
            "  4) Curvas por fase (ataque/sustain/cuerpo)",
            "  5) Café+EQ vs Azul (fidelidad de copia)",
            "  6) RC + composición con EQ fiel",
            "  7) Puntos clave vs informe V4.1",
        ],
    )


def _plot_cafe_azul_spectra(pdf: PdfPages, paths: RepoPaths, m) -> None:
    keys = ["B_12", "A_12", "E_12", "C_chromatic", "G_12", "C_24"]
    keys = [k for k in keys if k in m.PAIRS]
    fig, axes = plt.subplots(2, 3, figsize=(11.69, 8.27))
    fig.suptitle(
        "1. Espectros Café vs Azul (Welch, frames activos)",
        fontsize=14,
        fontweight="bold",
    )
    for ax, key in zip(axes.ravel(), keys):
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        fc, Sc = _spectrum_db(yc, m.SR)
        fa, Sa = _spectrum_db(ya, m.SR)
        # Align to common f
        f = fc
        Sa_i = _interp(fa, Sa, f)
        ax.semilogx(f, Sc, color="#8B4513", lw=1.3, label="Café")
        ax.semilogx(f, Sa_i, color="#1f4e79", lw=1.3, label="Azul")
        ax.set_xlim(30, 12000)
        ax.set_title(key)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.legend(fontsize=7, loc="lower left")
    for ax in axes.ravel()[len(keys) :]:
        ax.axis("off")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)

    # Mean delta page
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    fig.suptitle(
        "1b. Diferencia espectral Azul − Café (por pareja, sin EQ)",
        fontsize=14,
        fontweight="bold",
    )
    for key in keys:
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        fc, Sc = _spectrum_db(yc, m.SR)
        fa, Sa = _spectrum_db(ya, m.SR)
        d = _interp(fa, Sa, fc) - Sc
        ax.semilogx(fc, d, lw=1.1, alpha=0.85, label=key)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(30, 12000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8, ncol=3)
    ax.set_title("Incluye nivel + timbre (por eso ~−12 dB de offset global)")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)


def _plot_operative(
    pdf: PdfPages, out: Path, gain: float, variant: str
) -> tuple[np.ndarray, np.ndarray]:
    op = pd.read_csv(out / "CURVA_COPIA_OPERATIVA.csv")
    f = op.frequency_hz.to_numpy(float)
    y = op.eq_copy_db.to_numpy(float)
    total = y + gain

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle(
        f"2. EQ operativa fiel — {variant}  (gain {gain:+.2f} dB)",
        fontsize=13,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ax.semilogx(f, y, color="#0b6e4f", lw=2.0, label="eq_copy (timbre)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 18000)
    ax.set_title("Timbre (sin gain)")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.semilogx(f, total, color="#c45c26", lw=2.0, label="timbre + gain")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 18000)
    ax.set_title("Total a aplicar al Café")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    msk = f <= 350
    ax.plot(f[msk], y[msk], color="#0b6e4f", lw=1.8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("Zoom ≤350 Hz")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")

    ax = axes[1, 1]
    msk = (f >= 500) & (f <= 8000)
    ax.semilogx(f[msk], y[msk], color="#0b6e4f", lw=1.8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("Zoom 0.5–8 kHz (copia crítica)")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)
    return f, y


def _plot_all_transfers(pdf: PdfPages, out: Path, f_op, y_op) -> None:
    grid = np.geomspace(25, 16000, 2000)
    series = []

    def add(label, path, col, color, lw=1.4, ls="-"):
        cur = _read_curve(path, col)
        if cur is None:
            return
        series.append((label, _interp(cur[0], cur[1], grid), color, lw, ls))

    add("V10.2 central", out / "CURVAS_DENSAS_V10_2.csv", "precise_central_db", "#666", 1.2)
    add("V10.2 robust", out / "CURVAS_DENSAS_V10_2.csv", "precise_robust_db", "#999", 1.0, "--")
    add("V12 energy-neutral", out / "CURVAS_DENSAS_V12.csv", "energy_neutral_db", "#6a4c93", 1.3)
    add("V12 recommended (shrink)", out / "CURVAS_DENSAS_V12.csv", "recommended_db", "#6a4c93", 1.0, ":")
    add("V14 pair-first", out / "CURVAS_DENSAS_V14.csv", "energy_neutral_db", "#bc6c25", 1.2)
    add("V15 faithful", out / "CURVAS_DENSAS_V15_FIEL.csv", "eq_faithful_db", "#1d3557", 1.5)
    add("V16 faithful", out / "CURVAS_DENSAS_V16_FIEL.csv", "eq_faithful_db", "#457b9d", 1.3)
    series.append(
        ("V17 operativa (copia)", _interp(f_op, y_op, grid), "#0b6e4f", 2.2, "-")
    )

    fig, axes = plt.subplots(2, 1, figsize=(11.69, 8.27), sharex=False)
    fig.suptitle(
        "3. Todas las curvas de transferencia Café → Azul",
        fontsize=14,
        fontweight="bold",
    )
    ax = axes[0]
    for label, y, color, lw, ls in series:
        ax.semilogx(grid, y, label=label, color=color, lw=lw, ls=ls)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlim(25, 16000)
    ax.set_ylim(-8, 16)
    ax.set_ylabel("dB")
    ax.set_title("Comparación completa (timbre, sin gain global)")
    ax.legend(fontsize=7, ncol=2, loc="upper left")

    ax = axes[1]
    msk = (grid >= 400) & (grid <= 8000)
    for label, y, color, lw, ls in series:
        ax.semilogx(grid[msk], y[msk], label=label, color=color, lw=lw, ls=ls)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlim(400, 8000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("Zoom presencia / medios (0.4–8 kHz)")
    ax.legend(fontsize=7, ncol=2, loc="best")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)

    # V4.1 landmark overlay
    v41 = {
        98: -0.76,
        515: 3.49,
        958: 3.49,
        1360: 4.08,
        2630: 6.61,
        4120: 6.34,
        5190: 4.33,
    }
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.semilogx(grid, _interp(f_op, y_op, grid), color="#0b6e4f", lw=2.2, label="V17 operativa")
    v15 = _read_curve(out / "CURVAS_DENSAS_V15_FIEL.csv", "eq_faithful_db")
    if v15:
        ax.semilogx(grid, _interp(v15[0], v15[1], grid), color="#1d3557", lw=1.3, label="V15")
    v12 = _read_curve(out / "CURVAS_DENSAS_V12.csv", "energy_neutral_db")
    if v12:
        ax.semilogx(grid, _interp(v12[0], v12[1], grid), color="#6a4c93", lw=1.2, label="V12")
    ax.scatter(
        list(v41.keys()),
        list(v41.values()),
        s=55,
        color="#e63946",
        zorder=5,
        label="V4.1 puntos informe",
    )
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlim(40, 10000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("3b. Operativa vs puntos V4.1 (referencia analítica, no verdad absoluta)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _plot_phases(pdf: PdfPages, out: Path) -> None:
    path = out / "CURVAS_POR_FASE_V13.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    f = df.frequency_hz.to_numpy(float)
    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle("4. Curvas por fase temporal (V13)", fontsize=14, fontweight="bold")
    panels = [
        (axes[0, 0], ["attack_db", "sustain_db", "body_db"], "Ataque / sustain / cuerpo"),
        (axes[0, 1], ["attack_minus_body_db"], "Ataque − cuerpo"),
        (axes[1, 0], ["stabilization_db", "decay_db"], "Estabilización / decay"),
        (axes[1, 1], ["sustain_db"], "Sustain (detalle)"),
    ]
    for ax, cols, title in panels:
        for c in cols:
            if c in df.columns:
                ax.semilogx(f, df[c], lw=1.5, label=c.replace("_db", ""))
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(25, 12000)
        ax.set_title(title)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.legend(fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)


def _plot_fidelity_copy(pdf: PdfPages, paths: RepoPaths, m, f_op, y_op, gain: float) -> None:
    """Café raw / Café+EQ / Azul for proof pairs."""
    keys = ["B_12", "A_12", "E_12", "G_12"]
    keys = [k for k in keys if k in m.PAIRS]
    h = m.fir_from_curve(y_op)

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle(
        f"5. Fidelidad de copia: Café → (+EQ+gain {gain:+.2f} dB) vs Azul",
        fontsize=13,
        fontweight="bold",
    )
    for ax, key in zip(axes.ravel(), keys):
        p = m.PAIRS[key]
        yc, _ = m.load(p["cafe"])
        ya, _ = m.load(p["azul"])
        z = m.apply_eq(yc, h, gain)
        L = min(len(z), len(ya), len(yc))
        fc, Sc = _spectrum_db(yc[:L], m.SR)
        _, Sz = _spectrum_db(z[:L], m.SR)
        fa, Sa = _spectrum_db(ya[:L], m.SR)
        Sa_i = _interp(fa, Sa, fc)
        ax.semilogx(fc, Sc, color="#8B4513", lw=1.1, alpha=0.8, label="Café")
        ax.semilogx(fc, Sz, color="#0b6e4f", lw=1.5, label="Café+EQ")
        ax.semilogx(fc, Sa_i, color="#1f4e79", lw=1.3, label="Azul")
        ax.set_xlim(40, 10000)
        ax.set_title(key)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")
        ax.legend(fontsize=7)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)

    # Ranking table if present
    rank_path = _results_dir(paths) / "FIDELIDAD_RANKING_HOLDOUT_V17.csv"
    if rank_path.exists():
        rank = pd.read_csv(rank_path).head(8)
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle("5b. Ranking hold-out (V17)", fontsize=14, fontweight="bold")
        ax = fig.add_subplot(111)
        ax.axis("off")
        cols = [c for c in rank.columns if c in (
            "variant", "holdout_critical_rmse_db", "bias_2k4k_db", "gain_db", "presence_scale"
        )]
        cell = []
        for _, r in rank.iterrows():
            row = []
            for c in cols:
                v = r[c]
                if isinstance(v, float):
                    row.append(f"{v:.3f}" if np.isfinite(v) else "")
                else:
                    row.append(str(v)[:40])
            cell.append(row)
        table = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.5)
        pdf.savefig(fig)
        plt.close(fig)


def _plot_rc_with_faithful(pdf: PdfPages, paths: RepoPaths, f_op, y_op, gain: float) -> None:
    try:
        rc = load_rc(paths)
        curves = rc.load_refined_curves()
    except Exception as exc:  # noqa: BLE001
        _page_text(pdf, "6. RC", [f"No se pudieron cargar curvas RC: {exc}"])
        return

    f = curves.frequency_hz
    azul_y = _interp(f_op, y_op, f) + gain

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle(
        f"6. RC + EQ fiel Azul (gain {gain:+.2f} dB)",
        fontsize=14,
        fontweight="bold",
    )
    ax = axes[0, 0]
    ax.semilogx(f, azul_y, color="#0b6e4f", lw=2.0, label="Azul fiel (+gain)")
    for key, label in SETUP_LABELS.items():
        ax.semilogx(f, curves.setup_db(key), lw=1.2, label=f"RC {label}")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlim(20, 18000)
    ax.set_title("Componentes")
    ax.legend(fontsize=7)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")

    for ax, key, label in (
        (axes[0, 1], "bass", "Bajo"),
        (axes[1, 0], "hybrid", "Híbrido"),
        (axes[1, 1], "guitar", "Guitarra"),
    ):
        rc_y = curves.setup_db(key)
        ax.semilogx(f, azul_y, label="Azul fiel", lw=1.2, alpha=0.75)
        ax.semilogx(f, rc_y, label="RC", lw=1.2, alpha=0.75)
        ax.semilogx(f, azul_y + rc_y, label="Azul+RC", lw=2.0, color="#1b6ca8")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlim(20, 18000)
        ax.set_title(f"Composición {label}")
        ax.legend(fontsize=7)
        ax.set_xlabel("Hz")
        ax.set_ylabel("dB")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)


def _closing(pdf: PdfPages, out: Path, gain: float, variant: str) -> None:
    pts = []
    for hz in (98, 515, 958, 1360, 2630, 4120, 5190):
        op = pd.read_csv(out / "CURVA_COPIA_OPERATIVA.csv")
        y = float(np.interp(np.log(hz), np.log(op.frequency_hz), op.eq_copy_db))
        pts.append(f"  {hz:5g} Hz → {y:+.2f} dB")
    _page_text(
        pdf,
        "7. Cierre — estado de la copia Azul",
        [
            f"EQ operativa: {variant}",
            f"Gain: {gain:+.3f} dB  (reducir el Café)",
            "Smoothing: none",
            "",
            "Puntos de la curva operativa:",
            *pts,
            "",
            "Archivos clave:",
            "  · CURVA_COPIA_OPERATIVA.csv / GAIN_COPIA_OPERATIVA.csv",
            "  · FIDELIDAD_SIN_SUAVIZAR.md / MAPA_METODOLOGICO_V41_ULTRAPROFUNDO.md",
            "  · Audios: renders/FIDELIDAD_V17/ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac",
            "",
            "Límite actual: 16 parejas AAC. V18 (phase-first, event-conf) no mejoró",
            "el hold-out. El siguiente salto real es nueva evidencia (WAV/DI), no más",
            "agregadores sobre los mismos M4A.",
            "",
            "Presets MOOER Azul+RC: no regenerados aquí (presencia aún frágil).",
            "Este PDF documenta la EQ fiel y todas las curvas Café/Azul.",
        ],
    )


def generate_azul_fidelity_report(
    output_pdf: str | Path | None = None,
    *,
    paths: RepoPaths | None = None,
) -> dict:
    """Write a full Café→Azul review PDF with spectra and all transfer curves."""
    _style()
    paths = paths or discover_repo()
    out = _results_dir(paths)
    if output_pdf is None:
        output_pdf = paths.repo / "INFORME_COPIA_AZUL_FIEL.pdf"
    output_pdf = Path(output_pdf)

    m, _v15 = _load_build(paths)
    op = pd.read_csv(out / "CURVA_COPIA_OPERATIVA.csv")
    gain_row = pd.read_csv(out / "GAIN_COPIA_OPERATIVA.csv").iloc[0]
    gain = float(gain_row["gain_recommended_db"])
    variant = str(op.source_variant.iloc[0]) if "source_variant" in op.columns else "operative"

    hold = None
    for rank_name in (
        "FIDELIDAD_RANKING_HOLDOUT_V19.csv",
        "FIDELIDAD_RANKING_HOLDOUT_V17.csv",
        "RESUMEN_V19.json",
    ):
        rank = out / rank_name
        if not rank.exists():
            continue
        if rank.suffix == ".json":
            hold = float(json.loads(rank.read_text()).get("holdout_rmse_db", float("nan")))
            if np.isfinite(hold):
                break
            continue
        rdf = pd.read_csv(rank)
        # Prefer the row matching operative variant when present.
        if "variant" in rdf.columns and "source_variant" in op.columns:
            hit = rdf[rdf.variant.astype(str) == str(op.source_variant.iloc[0])]
            if len(hit):
                hold = float(hit.iloc[0]["holdout_critical_rmse_db"])
                break
        if "holdout_critical_rmse_db" in rdf.columns:
            hold = float(rdf.iloc[0]["holdout_critical_rmse_db"])
            break

    with PdfPages(output_pdf) as pdf:
        _cover(pdf, output_pdf, gain, variant, hold)
        print("PDF: cafe/azul spectra...", flush=True)
        _plot_cafe_azul_spectra(pdf, paths, m)
        print("PDF: operative EQ...", flush=True)
        f_op, y_op = _plot_operative(pdf, out, gain, variant)
        print("PDF: all transfers...", flush=True)
        _plot_all_transfers(pdf, out, f_op, y_op)
        print("PDF: phases...", flush=True)
        _plot_phases(pdf, out)
        print("PDF: fidelity copy...", flush=True)
        _plot_fidelity_copy(pdf, paths, m, f_op, y_op, gain)
        print("PDF: RC composition...", flush=True)
        _plot_rc_with_faithful(pdf, paths, f_op, y_op, gain)
        _closing(pdf, out, gain, variant)
        d = pdf.infodict()
        d["Title"] = "Informe copia fiel Café→Azul"
        d["Author"] = "unified orchestrator"
        d["Subject"] = f"{variant} gain={gain:.3f}dB"

    summary = {
        "pdf": str(output_pdf),
        "results_dir": str(out),
        "operative_variant": variant,
        "gain_db": gain,
        "holdout_rmse_db": hold,
        "pages": [
            "cover_review",
            "cafe_azul_spectra",
            "cafe_azul_delta",
            "operative_eq",
            "all_transfers",
            "v41_landmarks",
            "phase_curves",
            "fidelity_copy",
            "holdout_ranking",
            "rc_composition",
            "closing",
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = paths.unified / "data" / "informe_copia_azul_fiel_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    return summary
