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
    """Prefer the newest `_runs/*/results` that holds an operative curve."""
    runs = paths.emulate_azul / "_runs"
    candidates: list[Path] = []
    if runs.is_dir():
        for p in runs.glob("*/results"):
            if (p / "CURVA_COPIA_OPERATIVA.csv").exists():
                candidates.append(p)
    if candidates:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]
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


def _operative_meta(op: pd.DataFrame) -> dict:
    """Labels and metadata for the current operative curve (must track pipeline_version)."""
    row = op.iloc[0]
    source = str(row["source_variant"]) if "source_variant" in op.columns else "operative"
    air = str(row["air_policy"]) if "air_policy" in op.columns else ""
    pipe = str(row["pipeline_version"]) if "pipeline_version" in op.columns else ""
    # Prefer explicit pipeline_version (e.g. V20.0-operative) over the base+air source string.
    if pipe:
        short = pipe.replace("-operative", "").strip()
        label = f"{short} operativa"
        if air and air not in ("none", "", "nan"):
            label = f"{label} · air {air}"
    elif source.startswith("v19") and "+v20" in source:
        label = f"V20 operativa · {source}"
    else:
        label = f"operativa · {source}"
    return {
        "source_variant": source,
        "air_policy": air,
        "pipeline_version": pipe,
        "label": label,
        "short_label": (pipe.replace("-operative", "").strip() if pipe else "operativa"),
    }


def _holdout_from_results(out: Path, op: pd.DataFrame) -> float | None:
    """Prefer V20 resumen/ranking; fall back to older hold-out files."""
    # 1) Authoritative V20 summary written by improve_v20
    for name in (
        "RESUMEN_V22.json",
        "RESUMEN_V21.json",
        "RESUMEN_V20.json",
        "RESUMEN_V19.json",
        "RESUMEN_V17.json",
    ):
        path = out / name
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        hold = float(data.get("holdout_rmse_db", float("nan")))
        if np.isfinite(hold):
            return hold

    source = str(op.source_variant.iloc[0]) if "source_variant" in op.columns else ""
    air = str(op.air_policy.iloc[0]) if "air_policy" in op.columns else ""
    for rank_name in (
        "FIDELIDAD_RANKING_AIRE_V22.csv",
        "FIDELIDAD_RANKING_FORMA_V22.csv",
        "FIDELIDAD_RANKING_AIRE_V21.csv",
        "FIDELIDAD_RANKING_HOLDOUT_V21.csv",
        "FIDELIDAD_RANKING_AIRE_V20.csv",
        "FIDELIDAD_RANKING_HOLDOUT_V19.csv",
        "FIDELIDAD_RANKING_HOLDOUT_V18.csv",
        "FIDELIDAD_RANKING_HOLDOUT_V17.csv",
    ):
        rank = out / rank_name
        if not rank.exists():
            continue
        rdf = pd.read_csv(rank)
        if "variant" not in rdf.columns or "holdout_critical_rmse_db" not in rdf.columns:
            continue
        for key in (source, air, source.split("+")[-1] if "+" in source else ""):
            if not key:
                continue
            hit = rdf[rdf.variant.astype(str) == key]
            if len(hit):
                return float(hit.iloc[0]["holdout_critical_rmse_db"])
        return float(rdf.iloc[0]["holdout_critical_rmse_db"])
    return None


def _spectrum_db(y: np.ndarray, sr: int, nperseg: int = 8192):
    y = y - np.mean(y)
    n = max(int(0.02 * sr), 1)
    fr = y[: len(y) // n * n].reshape(-1, n)
    e = np.sqrt(np.mean(fr**2, axis=1))
    act = fr[e > 0.2 * e.max()].ravel() if e.max() > 0 else y
    f, P = _sig.welch(act, sr, nperseg=min(nperseg, max(256, len(act) // 4)))
    return f, 10 * np.log10(np.maximum(P, 1e-30))


def _cover(
    pdf: PdfPages,
    out: Path,
    gain: float,
    meta: dict,
    hold: float | None,
) -> None:
    hold_s = f"{hold:.3f} dB" if hold is not None and np.isfinite(hold) else "n/d"
    air = meta.get("air_policy") or "n/d"
    pipe = meta.get("pipeline_version") or meta["label"]
    _page_text(
        pdf,
        "Informe Café → Azul — copia fiel (sin suavizar)",
        [
            f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"PDF: {out.name}",
            "",
            "Repasada general (evidencia = 16 parejas AAC / 32 M4A):",
            "  · Separación nivel vs timbre: gain ≈ −12 dB (consenso V12/V15/V17/V4.1)",
            f"  · EQ operativa: {meta['label']}",
            f"  · pipeline_version: {pipe}",
            f"  · source_variant: {meta['source_variant']}",
            f"  · air_policy: {air}",
            f"  · Gain operativa: {gain:+.3f} dB",
            f"  · Hold-out crítico 0.5–8 kHz: {hold_s}",
            "  · Sin suavizado regional ni contracción EQ×reliability",
            "  · Aire 10–18 kHz: taper V20 (eq_copy ≠ V19 cruda encima de 10 kHz)",
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
            "  2) EQ operativa V20 + total con gain (+ taper aire)",
            "  3) Todas las curvas de transferencia (V10.2…V20)",
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
    pdf: PdfPages, out: Path, gain: float, meta: dict
) -> tuple[np.ndarray, np.ndarray]:
    op = pd.read_csv(out / "CURVA_COPIA_OPERATIVA.csv")
    f = op.frequency_hz.to_numpy(float)
    y = op.eq_copy_db.to_numpy(float)
    total = y + gain
    y_before = (
        op.eq_before_air_taper_db.to_numpy(float)
        if "eq_before_air_taper_db" in op.columns
        else None
    )

    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    fig.suptitle(
        f"2. EQ operativa fiel — {meta['label']}  (gain {gain:+.2f} dB)",
        fontsize=12,
        fontweight="bold",
    )

    ax = axes[0, 0]
    if y_before is not None:
        ax.semilogx(
            f,
            y_before,
            color="#7a9e8a",
            lw=1.2,
            ls="--",
            label="antes taper aire (base V19)",
        )
    ax.semilogx(f, y, color="#0b6e4f", lw=2.0, label="eq_copy V20 (operativa)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 18000)
    ax.set_title("Timbre (sin gain)")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=7)

    ax = axes[0, 1]
    ax.semilogx(f, total, color="#c45c26", lw=2.0, label="timbre + gain")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(20, 18000)
    ax.set_title("Total a aplicar al Café")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    msk = (f >= 500) & (f <= 8000)
    ax.semilogx(f[msk], y[msk], color="#0b6e4f", lw=1.8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("Zoom 0.5–8 kHz (copia crítica)")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")

    ax = axes[1, 1]
    msk = f >= 6000
    if y_before is not None:
        ax.semilogx(
            f[msk],
            y_before[msk],
            color="#7a9e8a",
            lw=1.3,
            ls="--",
            label="antes taper",
        )
    ax.semilogx(f[msk], y[msk], color="#0b6e4f", lw=2.0, label="eq_copy V20")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(6000, 18000)
    air = meta.get("air_policy") or "taper"
    ax.set_title(f"Zoom aire 6–18 kHz ({air})")
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=7)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)
    return f, y


def _plot_all_transfers(pdf: PdfPages, out: Path, f_op, y_op, meta: dict) -> None:
    grid = np.geomspace(25, 18000, 2000)
    series = []
    op_label = meta["label"]

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
    add(
        "V19 presence_robust (base)",
        out / "CURVAS_DENSAS_V19.csv",
        "faithful_v19_presence_robust_db",
        "#b08968",
        1.4,
        "--",
    )
    series.append(
        (op_label, _interp(f_op, y_op, grid), "#0b6e4f", 2.2, "-")
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
    ax.set_xlim(25, 18000)
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
    ax.semilogx(grid, _interp(f_op, y_op, grid), color="#0b6e4f", lw=2.2, label=op_label)
    v19 = _read_curve(out / "CURVAS_DENSAS_V19.csv", "faithful_v19_presence_robust_db")
    if v19:
        ax.semilogx(
            grid,
            _interp(v19[0], v19[1], grid),
            color="#b08968",
            lw=1.3,
            ls="--",
            label="V19 presence_robust (base, sin taper aire)",
        )
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
    ax.set_xlim(40, 18000)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("3b. Operativa V20 vs V19 base / puntos V4.1")
    ax.legend(fontsize=8)
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

    # Ranking table: prefer V20 air race, then newer hold-out rankings
    results = _results_dir(paths)
    rank_path = None
    rank_title = "5b. Ranking hold-out"
    for name, title in (
        ("FIDELIDAD_RANKING_FORMA_V22.csv", "5b. Ranking forma agudos V22"),
        ("FIDELIDAD_RANKING_AIRE_V22.csv", "5b. Ranking aire V22 (operativa actual)"),
        ("FIDELIDAD_RANKING_AIRE_V21.csv", "5b. Ranking aire V21"),
        ("FIDELIDAD_RANKING_HOLDOUT_V21.csv", "5b. Ranking hold-out V21"),
        ("FIDELIDAD_RANKING_AIRE_V20.csv", "5b. Ranking aire V20"),
        ("FIDELIDAD_RANKING_HOLDOUT_V19.csv", "5b. Ranking hold-out V19 (base)"),
        ("FIDELIDAD_RANKING_HOLDOUT_V18.csv", "5b. Ranking hold-out V18"),
        ("FIDELIDAD_RANKING_HOLDOUT_V17.csv", "5b. Ranking hold-out V17"),
    ):
        cand = results / name
        if cand.exists():
            rank_path = cand
            rank_title = title
            break
    if rank_path is not None:
        rank = pd.read_csv(rank_path).head(8)
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle(rank_title, fontsize=14, fontweight="bold")
        ax = fig.add_subplot(111)
        ax.axis("off")
        preferred = (
            "variant",
            "holdout_critical_rmse_db",
            "bias_2k4k_db",
            "bias_8k12k_db",
            "eq_at_10k_db",
            "eq_at_15k_db",
            "eq_at_18k_db",
            "gain_db",
            "presence_scale",
        )
        cols = [c for c in preferred if c in rank.columns]
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


def _closing(pdf: PdfPages, out: Path, gain: float, meta: dict) -> None:
    op = pd.read_csv(out / "CURVA_COPIA_OPERATIVA.csv")
    pts = []
    for hz in (98, 515, 958, 1360, 2630, 4120, 5190, 8000, 10000, 15000, 18000):
        y = float(np.interp(np.log(hz), np.log(op.frequency_hz), op.eq_copy_db))
        pts.append(f"  {hz:5g} Hz → {y:+.2f} dB")
    air = meta.get("air_policy") or "n/d"
    _page_text(
        pdf,
        "7. Cierre — estado de la copia Azul",
        [
            f"EQ operativa: {meta['label']}",
            f"pipeline_version: {meta.get('pipeline_version') or 'n/d'}",
            f"source_variant: {meta['source_variant']}",
            f"air_policy: {air}",
            f"Gain: {gain:+.3f} dB  (reducir el Café)",
            "Smoothing: none",
            "",
            "Puntos de la curva operativa (eq_copy_db = V20 con taper aire):",
            *pts,
            "",
            "Archivos clave:",
            "  · CURVA_COPIA_OPERATIVA.csv / GAIN_COPIA_OPERATIVA.csv",
            "  · RESUMEN_V20.json / FIDELIDAD_RANKING_AIRE_V20.csv",
            "  · FIDELIDAD_SIN_SUAVIZAR.md / MAPA_METODOLOGICO_V41_ULTRAPROFUNDO.md",
            "  · Audios: renders/FIDELIDAD_V20/…",
            "",
            "Nota: la base de presencia es V19 presence_robust; la EQ operativa",
            "actual es V20 (taper aire 10–18 kHz). No confundir con la curva V19.",
            "",
            "Límite actual: 16 parejas AAC. El siguiente salto real es nueva",
            "evidencia (WAV/DI), no más agregadores sobre los mismos M4A.",
            "",
            "Presets MOOER Azul+RC: no regenerados aquí (presencia aún frágil).",
            "Este PDF documenta la EQ fiel V20 y todas las curvas Café/Azul.",
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
    meta = _operative_meta(op)
    hold = _holdout_from_results(out, op)

    with PdfPages(output_pdf) as pdf:
        _cover(pdf, output_pdf, gain, meta, hold)
        print("PDF: cafe/azul spectra...", flush=True)
        _plot_cafe_azul_spectra(pdf, paths, m)
        print("PDF: operative EQ...", flush=True)
        f_op, y_op = _plot_operative(pdf, out, gain, meta)
        print("PDF: all transfers...", flush=True)
        _plot_all_transfers(pdf, out, f_op, y_op, meta)
        print("PDF: phases...", flush=True)
        _plot_phases(pdf, out)
        print("PDF: fidelity copy...", flush=True)
        _plot_fidelity_copy(pdf, paths, m, f_op, y_op, gain)
        print("PDF: RC composition...", flush=True)
        _plot_rc_with_faithful(pdf, paths, f_op, y_op, gain)
        _closing(pdf, out, gain, meta)
        d = pdf.infodict()
        d["Title"] = f"Informe copia fiel Café→Azul — {meta['short_label']}"
        d["Author"] = "unified orchestrator"
        d["Subject"] = f"{meta['source_variant']} air={meta.get('air_policy')} gain={gain:.3f}dB"

    summary = {
        "pdf": str(output_pdf),
        "results_dir": str(out),
        "operative_variant": meta["source_variant"],
        "operative_label": meta["label"],
        "pipeline_version": meta.get("pipeline_version"),
        "air_policy": meta.get("air_policy"),
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
