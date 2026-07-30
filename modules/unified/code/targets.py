"""Build optimization targets from Azul and optional RC curves."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bridge import load_azul, load_rc
from paths import RepoPaths, discover_repo


DEFAULT_GRID = 20.0 * 2.0 ** (np.arange(int(np.log2(18000 / 20) * 192) + 1) / 192)
DEFAULT_GRID = DEFAULT_GRID[DEFAULT_GRID <= 18000]


@dataclass
class FitTarget:
    name: str
    frequency_hz: np.ndarray
    target_db: np.ndarray
    uncertainty_db: np.ndarray
    meta: dict


def _interp_log(src_f: np.ndarray, src_y: np.ndarray, dst_f: np.ndarray) -> np.ndarray:
    return np.interp(np.log(dst_f), np.log(src_f), src_y)


def azul_target(
    *,
    variant: str = "central",
    include_gain: bool = True,
    frequency_hz: np.ndarray | None = None,
    paths: RepoPaths | None = None,
) -> FitTarget:
    """Target = Café→Azul transfer (timbre ± global gain)."""
    paths = paths or discover_repo()
    azul = load_azul(paths)
    curve = azul.load_curve()
    gain_row = azul.load_gain().iloc[0]
    gain = float(gain_row["gain_recommended_db"]) if include_gain else 0.0
    freq = np.asarray(frequency_hz if frequency_hz is not None else DEFAULT_GRID, dtype=float)

    # 'total' already includes gain in results; for other variants we add it optionally.
    if variant == "total":
        y = curve.interpolate(freq, "total")
        used_gain = float(gain_row["gain_recommended_db"])
    else:
        y = curve.interpolate(freq, variant) + gain
        used_gain = gain

    # Uncertainty proxy from support: less support → higher unc.
    if curve.support_state is not None:
        # Map support labels roughly; unknown → mid uncertainty.
        support = curve.support_state
        # Interpolate nearest support state on log-f grid via index.
        idx = np.clip(
            np.searchsorted(curve.frequency_hz, freq) - 1,
            0,
            len(curve.frequency_hz) - 1,
        )
        unc = np.array(
            [
                0.15
                if str(support[i]).lower().startswith("measured")
                else 0.35
                if "inference" in str(support[i]).lower()
                else 0.55
                for i in idx
            ],
            dtype=float,
        )
    else:
        unc = np.full_like(freq, 0.25)

    return FitTarget(
        name=f"azul_{variant}" + ("_with_gain" if include_gain or variant == "total" else "_timbre"),
        frequency_hz=freq,
        target_db=y,
        uncertainty_db=unc,
        meta={
            "mode": "azul",
            "azul_variant": variant,
            "include_gain": include_gain or variant == "total",
            "gain_db": used_gain,
        },
    )


def rc_target(
    *,
    rc_setup: str = "bass",
    frequency_hz: np.ndarray | None = None,
    paths: RepoPaths | None = None,
) -> FitTarget:
    """Target = measured RC pedal response (bass|hybrid|guitar)."""
    if rc_setup not in {"bass", "hybrid", "guitar"}:
        raise ValueError("rc_setup must be bass|hybrid|guitar")
    paths = paths or discover_repo()
    rc = load_rc(paths)
    curves = rc.load_refined_curves()
    freq = np.asarray(frequency_hz if frequency_hz is not None else curves.frequency_hz, dtype=float)
    y = _interp_log(curves.frequency_hz, curves.setup_db(rc_setup), freq)
    u = _interp_log(curves.frequency_hz, curves.uncertainties[rc_setup], freq)
    u = np.maximum(u, 0.08)
    return FitTarget(
        name=f"rc_{rc_setup}",
        frequency_hz=freq,
        target_db=y,
        uncertainty_db=u,
        meta={"mode": "rc", "rc_setup": rc_setup},
    )


def azul_rc_target(
    *,
    rc_setup: str = "bass",
    compose: str = "minus",
    azul_variant: str = "central",
    include_gain: bool = True,
    frequency_hz: np.ndarray | None = None,
    paths: RepoPaths | None = None,
) -> FitTarget:
    """Compose Azul with an RC setup.

    compose:
      - plus  : target = Azul + RC   (cascade both colorations)
      - minus : target = Azul - RC   (what Mooer must add if RC is already engaged)
    """
    if compose not in {"plus", "minus"}:
        raise ValueError("compose must be 'plus' or 'minus'")
    if rc_setup not in {"bass", "hybrid", "guitar"}:
        raise ValueError("rc_setup must be bass|hybrid|guitar")

    paths = paths or discover_repo()
    rc = load_rc(paths)
    curves = rc.load_refined_curves()
    freq = np.asarray(frequency_hz if frequency_hz is not None else curves.frequency_hz, dtype=float)

    base = azul_target(
        variant=azul_variant,
        include_gain=include_gain,
        frequency_hz=freq,
        paths=paths,
    )
    rc_y = _interp_log(curves.frequency_hz, curves.setup_db(rc_setup), freq)
    rc_u = _interp_log(curves.frequency_hz, curves.uncertainties[rc_setup], freq)

    gain_tag = "with_gain" if (include_gain or azul_variant == "total") else "timbre"
    if compose == "plus":
        target = base.target_db + rc_y
        name = f"azul_plus_rc_{rc_setup}_{gain_tag}"
    else:
        target = base.target_db - rc_y
        name = f"azul_minus_rc_{rc_setup}_{gain_tag}"

    unc = np.sqrt(base.uncertainty_db**2 + np.maximum(rc_u, 0.05) ** 2)
    meta = {
        **base.meta,
        "mode": f"azul_{compose}_rc",
        "rc_setup": rc_setup,
        "compose": compose,
    }
    return FitTarget(name=name, frequency_hz=freq, target_db=target, uncertainty_db=unc, meta=meta)
