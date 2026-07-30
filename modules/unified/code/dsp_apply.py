"""Apply magnitude transfer curves to audio (FIR + optional streaming OLA)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from audio_io import TARGET_SR


def fir_from_magnitude(
    frequency_hz: np.ndarray,
    gain_db: np.ndarray,
    *,
    sr: int = TARGET_SR,
    numtaps: int = 8193,
    beta: float = 7.5,
) -> np.ndarray:
    """Minimum-error linear-phase FIR from a dense magnitude curve (dB)."""
    f = np.asarray(frequency_hz, dtype=float)
    g = np.asarray(gain_db, dtype=float)
    order = np.argsort(f)
    f, g = f[order], g[order]
    # firwin2 needs 0 and Nyquist endpoints.
    f_nyq = sr / 2.0
    f_full = np.r_[0.0, np.clip(f, 1e-6, f_nyq - 1e-6), f_nyq]
    g_full = np.r_[g[0], g, g[-1]]
    # Deduplicate frequencies (firwin2 requires strictly increasing).
    keep = np.r_[True, np.diff(f_full) > 0]
    f_full, g_full = f_full[keep], g_full[keep]
    amp = 10.0 ** (g_full / 20.0)
    return signal.firwin2(numtaps, f_full / f_nyq, amp, window=("kaiser", beta)).astype(np.float64)


def apply_fir(y: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Offline linear convolution (same length), DC-centered like V10.2 render."""
    x = np.asarray(y, dtype=np.float64)
    x = x - np.mean(x)
    z = signal.fftconvolve(x, h, mode="same")
    return z.astype(np.float32)


@dataclass
class StreamingFIR:
    """Causal overlap-add FIR for near-realtime / block processing.

    Group delay is (len(h)-1)/2 samples vs offline ``mode='same'``.
    Use ``align_to_same=True`` in ``process()`` to match offline centering
    for fidelity checks (not for true live I/O).
    """

    h: np.ndarray
    block_size: int = 2048

    def __post_init__(self) -> None:
        self.h = np.asarray(self.h, dtype=np.float64)
        self._overlap = len(self.h) - 1
        self._state = np.zeros(self._overlap, dtype=np.float64)
        self.group_delay = (len(self.h) - 1) // 2

    def reset(self) -> None:
        self._state[:] = 0.0

    def process_block(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block, dtype=np.float64)
        # Full convolution of this block; OLA with previous tail.
        conv = signal.fftconvolve(x, self.h, mode="full")
        if self._overlap:
            conv[: self._overlap] += self._state
            self._state = conv[len(x) : len(x) + self._overlap].copy()
            if len(self._state) < self._overlap:
                self._state = np.pad(self._state, (0, self._overlap - len(self._state)))
        return conv[: len(x)].astype(np.float32)

    def process(self, y: np.ndarray, *, align_to_same: bool = True) -> np.ndarray:
        """Process whole buffer in blocks.

        If ``align_to_same``, delay-compensate so output matches offline
        ``fftconvolve(..., mode='same')`` (useful for fidelity; for live
        jack/portaudio keep ``align_to_same=False``).
        """
        self.reset()
        x = np.asarray(y, dtype=np.float64)
        x = x - np.mean(x)
        chunks = []
        for i in range(0, len(x), self.block_size):
            chunks.append(self.process_block(x[i : i + self.block_size]))
        # Flush filter memory.
        if self._overlap:
            chunks.append(self.process_block(np.zeros(self._overlap, dtype=np.float64)))
        z = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float64)
        if align_to_same:
            # Causal output starts earlier by group_delay vs centered 'same'.
            # Shift left by group_delay to align with mode='same'.
            d = self.group_delay
            aligned = np.zeros(len(x), dtype=np.float64)
            src = z[d : d + len(x)]
            aligned[: len(src)] = src
            return aligned.astype(np.float32)
        return z[: len(x)].astype(np.float32)

def measure_transfer_db(
    x: np.ndarray,
    y: np.ndarray,
    *,
    sr: int = TARGET_SR,
    nperseg: int = 8192,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate H(f) = Y/X in dB via Welch (fidelity check against intended curve)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    fx, px = signal.welch(x, fs=sr, nperseg=min(nperseg, n), scaling="spectrum")
    fy, py = signal.welch(y, fs=sr, nperseg=min(nperseg, n), scaling="spectrum")
    # Same grid from welch
    eps = 1e-20
    h_db = 10.0 * np.log10((py + eps) / (px + eps))
    return fx.astype(float), h_db.astype(float)


def compare_curves(
    freq_hz: np.ndarray,
    measured_db: np.ndarray,
    intended_f: np.ndarray,
    intended_db: np.ndarray,
    *,
    fmin: float = 30.0,
    fmax: float = 12000.0,
) -> dict[str, float]:
    """RMSE between measured transfer and intended magnitude curve."""
    m = (freq_hz >= fmin) & (freq_hz <= fmax) & (freq_hz > 0)
    f = freq_hz[m]
    meas = measured_db[m]
    intent = np.interp(np.log(f), np.log(intended_f), intended_db)
    err = meas - intent
    return {
        "rmse_db": float(np.sqrt(np.mean(err**2))),
        "mae_db": float(np.mean(np.abs(err))),
        "p95_abs_db": float(np.percentile(np.abs(err), 95)),
        "bias_db": float(np.mean(err)),
        "n_bins": int(m.sum()),
        "fmin": fmin,
        "fmax": fmax,
    }
