"""V20: air / ultra-highs policy (10–18 kHz) without smoothing presence.

Finding vs V4.1 presence/brillo/aire report:

* Our V19 operative still carries ~+3.7…+4.5 dB from 8–18 kHz because
  ``presence_scale`` multiplies everything ≥500 Hz.
* V4.1 treats 10–18 kHz as mostly diagnostic: attack-heavy, AAC prior
  0.72→0.08, wide smooth, then EQ×reliability → 0.
* We still refuse octave smooth and full reliability shrink on 0.5–8 kHz.
* For air only, we race explicit tapers toward 0 and keep the winner if
  0.5–8 kHz hold-out does not regress and 8–12 kHz bias improves.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent))

import numpy as np
import pandas as pd

from repo_paths import AUD, OUT, ensure_runtime_dirs

ensure_runtime_dirs()
sys.path.insert(0, str(_P(__file__).resolve().parent))

import build_v10_2 as m  # noqa: E402
import improve_v12 as v12  # noqa: E402
import improve_v15 as v15  # noqa: E402
import improve_v17 as v17  # noqa: E402
import run_manifest  # noqa: E402

CALIB = v17.CALIB_PAIRS
HOLD = v17.HOLD_PAIRS
CRIT = ["500-1k", "1k-2k", "2k-4k", "4k-8k"]


def air_taper_aac(curve: np.ndarray, freq: np.ndarray) -> np.ndarray:
    """Multiply EQ by AAC prior above 8 kHz (V4.1 §28 spirit, no smooth)."""
    y = curve.copy()
    prior = v12.codec_prior(freq)
    # Below 8 kHz prior=1 → unchanged. Above, shrink toward 0.
    y = y * prior
    return y


def air_taper_soft(curve: np.ndarray, freq: np.ndarray, f0: float = 8000.0, f1: float = 15000.0) -> np.ndarray:
    """Linear-in-log fade of EQ magnitude from f0→f1 toward 0."""
    y = curve.copy()
    lo, hi = np.log(f0), np.log(f1)
    lf = np.log(freq)
    t = np.clip((lf - lo) / (hi - lo), 0.0, 1.0)
    # Keep full below f0; fade to 0 by f1; stay 0 above.
    y = y * (1.0 - t)
    return y


def air_taper_hard10k(curve: np.ndarray, freq: np.ndarray) -> np.ndarray:
    y = curve.copy()
    y[freq >= 10000.0] = 0.0
    # Short crossfade 8–10 kHz
    sel = (freq >= 8000.0) & (freq < 10000.0)
    t = (np.log(freq[sel]) - np.log(8000.0)) / (np.log(10000.0) - np.log(8000.0))
    y[sel] = curve[sel] * (1.0 - t)
    return y


def air_taper_aac_then_soft(curve: np.ndarray, freq: np.ndarray) -> np.ndarray:
    return air_taper_soft(air_taper_aac(curve, freq), freq, 10000.0, 17000.0)


def score(curve: np.ndarray, gain: float, label: str, pairs: list[str]) -> dict:
    audit = v15.fidelity_audit(curve, gain, label, pairs=pairs)
    crit = audit[audit.band.isin(CRIT)]
    hi = audit[audit.band == "8k-12k"]
    return {
        "variant": label,
        "holdout_critical_rmse_db": float(crit.rmse_db.median()),
        "bias_2k4k_db": float(audit.loc[audit.band == "2k-4k", "bias_db"].median()),
        "bias_8k12k_db": float(hi.bias_db.median()) if len(hi) else np.nan,
        "rmse_8k12k_db": float(hi.rmse_db.median()) if len(hi) else np.nan,
        "gain_db": float(gain),
        "eq_at_10k_db": float(np.interp(np.log(10000), np.log(m.DENSE_F), curve)),
        "eq_at_15k_db": float(np.interp(np.log(15000), np.log(m.DENSE_F), curve)),
        "eq_at_18k_db": float(np.interp(np.log(18000), np.log(m.DENSE_F), curve)),
    }


def main() -> None:
    t0 = time.time()
    run_id = f"v20_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    manifest = run_manifest.build(
        run_id, pipeline="emulate_azul_v20", stages=["improve_v20"]
    )

    op = pd.read_csv(OUT / "CURVA_COPIA_OPERATIVA.csv")
    base = np.interp(np.log(m.DENSE_F), np.log(op.frequency_hz), op.eq_copy_db)
    gain = float(pd.read_csv(OUT / "GAIN_COPIA_OPERATIVA.csv").iloc[0].gain_recommended_db)
    src = str(op.source_variant.iloc[0])
    print(f"1 base operative {src} gain {gain:+.3f}", flush=True)
    def _at(hz: float) -> float:
        return float(np.interp(np.log(hz), np.log(m.DENSE_F), base))

    print(
        f"   air now: 10k={_at(10000):+.2f} 15k={_at(15000):+.2f} 18k={_at(18000):+.2f}",
        flush=True,
    )

    variants = {
        "v20_no_taper": base,
        "v20_aac_prior": air_taper_aac(base, m.DENSE_F),
        "v20_soft_8_15": air_taper_soft(base, m.DENSE_F, 8000, 15000),
        "v20_hard_10k": air_taper_hard10k(base, m.DENSE_F),
        "v20_aac_then_soft": air_taper_aac_then_soft(base, m.DENSE_F),
    }

    # Also show V12 recommended air policy as reference (already ~0 air).
    v12c = pd.read_csv(OUT / "CURVAS_DENSAS_V12.csv")
    c12r = np.interp(
        np.log(m.DENSE_F), np.log(v12c.frequency_hz), v12c.recommended_db
    )
    g12 = float(
        json.loads((OUT / "RESUMEN_V12.json").read_text())["gain_v12_energy_neutral_db"]
    )

    results = []
    print("2 hold-out race (critical bands + 8–12 kHz diagnostic)", flush=True)
    for name, curve in variants.items():
        row = score(curve, gain, name, HOLD)
        results.append(row)
        print(
            f"   {name}: critRMSE {row['holdout_critical_rmse_db']:.3f} "
            f"b2k4k {row['bias_2k4k_db']:+.3f} "
            f"b8k12 {row['bias_8k12k_db']:+.3f} "
            f"eq15k {row['eq_at_15k_db']:+.2f}",
            flush=True,
        )
    row = score(c12r, g12, "v12_recommended_ref", HOLD)
    results.append(row)

    ranking = pd.DataFrame(results)
    # Primary: do not worsen critical RMSE vs no_taper by >0.05.
    # Among those, minimize |bias_8k12| then |eq_at_15k| then critical RMSE.
    base_rmse = float(
        ranking.loc[ranking.variant == "v20_no_taper", "holdout_critical_rmse_db"].iloc[0]
    )
    ok = ranking[
        (ranking.variant.str.startswith("v20_"))
        & (ranking.holdout_critical_rmse_db <= base_rmse + 0.05)
    ].copy()
    ok["abs_b8"] = ok.bias_8k12k_db.abs()
    ok["abs_eq15"] = ok.eq_at_15k_db.abs()
    ok = ok.sort_values(
        ["abs_b8", "abs_eq15", "holdout_critical_rmse_db"]
    ).reset_index(drop=True)
    ranking.to_csv(OUT / "FIDELIDAD_RANKING_AIRE_V20.csv", index=False)
    print("\nfull ranking:", flush=True)
    print(ranking.round(3).to_string(index=False), flush=True)
    best = ok.iloc[0]
    best_name = str(best.variant)
    print(
        f"3 winner: {best_name} critRMSE={best.holdout_critical_rmse_db:.3f} "
        f"b8k12={best.bias_8k12k_db:+.3f} eq15k={best.eq_at_15k_db:+.2f}",
        flush=True,
    )

    op_curve = variants[best_name]
    # Publish
    pd.DataFrame(
        {
            "frequency_hz": m.DENSE_F,
            "eq_copy_db": op_curve,
            "eq_before_air_taper_db": base,
            "source_variant": f"{src}+{best_name}",
            "air_policy": best_name,
            "smoothing": "none",
            "pipeline_version": "V20.0-operative",
        }
    ).to_csv(OUT / "CURVA_COPIA_OPERATIVA.csv", index=False)
    # Keep gain from V19 (air taper is energy-light in highs).
    pd.DataFrame(
        [
            {
                "gain_recommended_db": gain,
                "gain_source": f"{src}+{best_name}",
                "air_policy": best_name,
                "smoothing": "none",
                "pipeline_version": "V20.0-operative",
            }
        ]
    ).to_csv(OUT / "GAIN_COPIA_OPERATIVA.csv", index=False)

    rows = {"frequency_hz": m.DENSE_F, "eq_before_air_db": base}
    for name, curve in variants.items():
        rows[f"{name}_db"] = curve
    rows["eq_operative_db"] = op_curve
    pd.DataFrame(rows).to_csv(OUT / "CURVAS_AIRE_V20.csv", index=False)

    # Landmark table
    pts = []
    for hz in (2500, 4000, 6000, 8000, 10000, 12000, 15000, 17000, 18000):
        pts.append(
            {
                "frequency_hz": hz,
                "before_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), base)),
                "operative_db": float(np.interp(np.log(hz), np.log(m.DENSE_F), op_curve)),
                "aac_prior": float(v12.codec_prior(np.array([hz]))[0]),
            }
        )
    pd.DataFrame(pts).to_csv(OUT / "COMPARACION_AIRE_V20.csv", index=False)
    print(pd.DataFrame(pts).round(3).to_string(index=False), flush=True)

    # Proof
    import soundfile as sf

    proof = AUD / "FIDELIDAD_V20"
    proof.mkdir(parents=True, exist_ok=True)
    p = m.PAIRS["B_12"]
    yc, _ = m.load(p["cafe"])
    ya, _ = m.load(p["azul"])
    z = m.apply_eq(yc, m.fir_from_curve(op_curve), gain)
    L = min(len(z), len(ya))
    sf.write(proof / "AZUL_ORIGINAL.flac", ya[:L], m.SR, subtype="PCM_24")
    sf.write(proof / "CAFE_COPIA_OPERATIVA.flac", z[:L], m.SR, subtype="PCM_24")
    sf.write(
        proof / "ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac",
        np.column_stack([z[:L], ya[:L]]),
        m.SR,
        subtype="PCM_24",
    )

    analysis = {
        "v41_air_policy": {
            "10_18_khz": "diagnostic; attack 80%/sustain 20%; AAC prior→0.08; smooth ~1/2 oct; EQ×reliability→0",
            "evidence_to": "~15.3 kHz at reliability≥0.15; ~9.8 kHz at ≥0.35",
        },
        "ours_before_v20": {
            "problem": "presence_scale≥500Hz left +3.7…+4.5 dB through 18 kHz",
            "better": "DPSS, F0 refine, acoustic match, render metric, no blind smooth",
            "already_had": "AAC prior in observation weights; phase mix 64/36 and 80/20; open>300 excluded",
        },
        "adopted_v20": {
            "what": "air taper toward 0 using AAC prior / soft fade — NOT presence smooth, NOT full reliability shrink on 0.5–8k",
            "winner": best_name,
        },
    }
    (OUT / "ANALISIS_AIRE_V20.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "run_id": run_id,
        "base_variant": src,
        "winner": best_name,
        "gain_db": gain,
        "holdout_rmse_db": float(best.holdout_critical_rmse_db),
        "bias_2k4k_db": float(best.bias_2k4k_db),
        "bias_8k12k_db": float(best.bias_8k12k_db),
        "eq_at_15k_db": float(best.eq_at_15k_db),
        "eq_at_18k_db": float(best.eq_at_18k_db),
        "ranking": ranking.to_dict("records"),
        "elapsed_s": time.time() - t0,
    }
    (OUT / "RESUMEN_V20.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "IMPLEMENTACION_FIEL_V20.json").write_text(
        json.dumps(
            {
                "version": "V20.0",
                "operative_curve_csv": "CURVA_COPIA_OPERATIVA.csv",
                "air_policy": best_name,
                "base": src,
                "gain_db": gain,
                "intent": "Keep faithful presence; treat 10–18 kHz as diagnostic air like V4.1 without smoothing mids.",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest.update(summary)
    run_manifest.finalize(manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
