"""Deterministic onset-strength envelope (no librosa dependency).

`build_v10_2` originally called `librosa.onset.onset_strength`. That made event
detection depend on the installed librosa version: re-running the published
pipeline produced 927 matched events instead of 873, which in turn moved the
2-4 kHz region of the Café→Azul curve by up to 2.3 dB.

This module reimplements the same estimator (Slaney mel filterbank → power in
dB → half-wave-rectified first difference → mean across mel bands) with numpy
and scipy only, so the result depends solely on the input signal and the
declared parameters.
"""
from __future__ import annotations

import numpy as np
from scipy import signal as _signal

# Slaney mel scale breakpoints.
_F_MIN = 0.0
_F_SP = 200.0 / 3.0
_MIN_LOG_HZ = 1000.0
_MIN_LOG_MEL = (_MIN_LOG_HZ - _F_MIN) / _F_SP
_LOGSTEP = np.log(6.4) / 27.0


def hz_to_mel(freq: np.ndarray) -> np.ndarray:
    freq = np.asarray(freq, dtype=float)
    mels = (freq - _F_MIN) / _F_SP
    log_t = freq >= _MIN_LOG_HZ
    mels[log_t] = _MIN_LOG_MEL + np.log(freq[log_t] / _MIN_LOG_HZ) / _LOGSTEP
    return mels


def mel_to_hz(mels: np.ndarray) -> np.ndarray:
    mels = np.asarray(mels, dtype=float)
    freqs = _F_MIN + _F_SP * mels
    log_t = mels >= _MIN_LOG_MEL
    freqs[log_t] = _MIN_LOG_HZ * np.exp(_LOGSTEP * (mels[log_t] - _MIN_LOG_MEL))
    return freqs


def mel_filterbank(
    sr: int,
    n_fft: int,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float | None = None,
) -> np.ndarray:
    """Slaney-normalised mel filterbank, shape (n_mels, 1 + n_fft // 2)."""
    if fmax is None:
        fmax = sr / 2.0
    fft_freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    mel_pts = np.linspace(hz_to_mel(np.array([fmin]))[0], hz_to_mel(np.array([fmax]))[0], n_mels + 2)
    hz_pts = mel_to_hz(mel_pts)

    fdiff = np.diff(hz_pts)
    ramps = hz_pts[:, None] - fft_freqs[None, :]

    weights = np.zeros((n_mels, len(fft_freqs)), dtype=float)
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0.0, np.minimum(lower, upper))

    # Slaney normalisation: equal area per filter.
    enorm = 2.0 / (hz_pts[2 : n_mels + 2] - hz_pts[:n_mels])
    weights *= enorm[:, None]
    return weights


def _stft_power(y: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    """Centered STFT power spectrogram with a periodic Hann window."""
    y = np.asarray(y, dtype=float)
    pad = n_fft // 2
    yp = np.pad(y, pad, mode="constant")
    window = _signal.windows.hann(n_fft, sym=False)

    n_frames = 1 + (len(yp) - n_fft) // hop_length
    if n_frames < 1:
        return np.zeros((1 + n_fft // 2, 0))
    idx = np.arange(n_fft)[None, :] + hop_length * np.arange(n_frames)[:, None]
    frames = yp[idx] * window[None, :]
    spec = np.fft.rfft(frames, n=n_fft, axis=1)
    return (np.abs(spec) ** 2).T


def melspectrogram(
    y: np.ndarray,
    sr: int,
    n_fft: int = 2048,
    hop_length: int = 512,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float | None = None,
) -> np.ndarray:
    power = _stft_power(y, n_fft, hop_length)
    fb = mel_filterbank(sr, n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax)
    return fb @ power


def power_to_db(S: np.ndarray, amin: float = 1e-10, top_db: float | None = 80.0) -> np.ndarray:
    """dB conversion referenced to the spectrogram maximum (librosa default)."""
    S = np.asarray(S, dtype=float)
    ref = float(np.max(S)) if S.size else 1.0
    log_spec = 10.0 * np.log10(np.maximum(amin, S))
    log_spec -= 10.0 * np.log10(max(amin, ref))
    if top_db is not None and log_spec.size:
        log_spec = np.maximum(log_spec, log_spec.max() - top_db)
    return log_spec


def onset_strength(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512,
    n_fft: int = 2048,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float | None = None,
    lag: int = 1,
    aggregate=np.mean,
) -> np.ndarray:
    """Half-wave-rectified spectral flux over a mel filterbank.

    Signature and framing match the ``librosa.onset.onset_strength`` call that
    ``build_v10_2`` used, so the returned envelope is frame-aligned with it.
    """
    S = melspectrogram(y, sr, n_fft=n_fft, hop_length=hop_length, n_mels=n_mels, fmin=fmin, fmax=fmax)
    S_db = power_to_db(S)
    n_frames = S_db.shape[-1]
    if n_frames <= lag:
        return np.zeros(max(n_frames, 0))

    flux = S_db[..., lag:] - S_db[..., :-lag]
    flux = np.maximum(0.0, flux)
    env = aggregate(flux, axis=-2)

    # librosa pads by `lag` plus the centering offset, then trims to n_frames.
    pad_width = lag + n_fft // (2 * hop_length)
    env = np.pad(env, (int(pad_width), 0), mode="constant")
    return env[:n_frames]
