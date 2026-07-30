"""Load / save arbitrary bass audio (wav/flac/m4a/…) @ 44.1 kHz mono."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

TARGET_SR = 44100


def _decode_ffmpeg(path: Path, sr: int = TARGET_SR) -> tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable file to mono float32 PCM."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sr),
            "-f",
            "f32le",
            str(out),
        ]
        # Prefer wav container for soundfile; rewrite as pcm_f32le wav.
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sr),
            "-c:a",
            "pcm_f32le",
            str(out),
        ]
        subprocess.run(cmd, check=True)
        y, file_sr = sf.read(out, always_2d=False)
    finally:
        out.unlink(missing_ok=True)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1).astype(np.float32)
    return y, int(file_sr)


def load_audio(path: str | Path, *, sr: int = TARGET_SR) -> tuple[np.ndarray, int]:
    """Load any bass audio file → mono float32 at `sr`.

    Accepts wav/flac/aiff via soundfile; falls back to ffmpeg for m4a/mp3/etc.
    Resamples with ffmpeg when needed (keeps fidelity, no librosa dependency).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix in {".wav", ".flac", ".aiff", ".aif", ".ogg"}:
        try:
            info = sf.info(str(path))
            if int(info.samplerate) == sr and info.channels == 1:
                y, file_sr = sf.read(str(path), always_2d=False, dtype="float32")
                y = np.asarray(y, dtype=np.float32)
                if y.ndim > 1:
                    y = y.mean(axis=1).astype(np.float32)
                return y, int(file_sr)
        except Exception:
            pass
        # Channels/SR mismatch or exotic subtype → ffmpeg normalize.
        return _decode_ffmpeg(path, sr=sr)

    return _decode_ffmpeg(path, sr=sr)


def save_audio(path: str | Path, y: np.ndarray, *, sr: int = TARGET_SR) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.asarray(y, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    # Soft protect against digital clip without rewriting the transfer.
    if peak > 1.0:
        y = (y / peak * 0.99).astype(np.float32)
    sf.write(str(path), y, sr, subtype="FLOAT")
    return path
