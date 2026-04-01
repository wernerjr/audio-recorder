from __future__ import annotations

import logging
import shutil
from math import gcd
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _read_offset(wav_path: Path) -> float:
    """Read the timestamp sidecar written by WavWriter, or 0.0 if absent."""
    offset_path = wav_path.with_suffix(".offset")
    if offset_path.exists():
        try:
            return float(offset_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return 0.0


def mix_wav(mic_path: Path, sys_path: Path, out_path: Path) -> Path:
    """
    Mix two WAV files into one, aligning sample rates and start times.

    WavWriter writes a <name>.offset sidecar with the wall-clock timestamp
    of the first chunk. This function reads both offsets and pads the
    later-starting channel with leading silence so the two tracks are
    correctly aligned in time.

    Both files must be PCM Int16 (the format WavWriter produces).
    If one file is missing the other is copied as-is.
    Returns *out_path*.
    """
    mic_ok = mic_path.exists() and mic_path.stat().st_size > 44
    sys_ok = sys_path.exists() and sys_path.stat().st_size > 44

    if not mic_ok and not sys_ok:
        raise FileNotFoundError(f"Neither {mic_path} nor {sys_path} found.")

    if not mic_ok:
        logger.warning("microfone.wav ausente — usando apenas sistema.wav")
        shutil.copy2(sys_path, out_path)
        return out_path

    if not sys_ok:
        logger.warning("sistema.wav ausente — usando apenas microfone.wav")
        shutil.copy2(mic_path, out_path)
        return out_path

    import scipy.io.wavfile as wav

    mic_sr, mic_data = wav.read(str(mic_path))
    sys_sr, sys_data = wav.read(str(sys_path))

    mic_f = _to_mono_float(mic_data)
    sys_f = _to_mono_float(sys_data)

    # Resample to the higher sample rate so no quality is lost
    target_sr = max(mic_sr, sys_sr)
    if mic_sr != target_sr:
        mic_f = _resample(mic_f, mic_sr, target_sr)
    if sys_sr != target_sr:
        sys_f = _resample(sys_f, sys_sr, target_sr)

    # Align channels using the sidecar offset files written by WavWriter
    mic_t0 = _read_offset(mic_path)
    sys_t0 = _read_offset(sys_path)
    delay_sec = sys_t0 - mic_t0  # positive → system started later than mic

    if delay_sec > 0:
        pad_samples = int(delay_sec * target_sr)
        sys_f = np.pad(sys_f, (pad_samples, 0))
        logger.debug("sistema.wav atrasado %.3fs → padding %d amostras", delay_sec, pad_samples)
    elif delay_sec < 0:
        pad_samples = int(-delay_sec * target_sr)
        mic_f = np.pad(mic_f, (pad_samples, 0))
        logger.debug("microfone.wav atrasado %.3fs → padding %d amostras", -delay_sec, pad_samples)

    # Equalise lengths with trailing silence
    diff = len(mic_f) - len(sys_f)
    if diff > 0:
        sys_f = np.pad(sys_f, (0, diff))
    elif diff < 0:
        mic_f = np.pad(mic_f, (0, -diff))

    mixed = np.clip(mic_f + sys_f, -1.0, 1.0)
    mixed_int16 = (mixed * 32767).astype(np.int16)

    wav.write(str(out_path), target_sr, mixed_int16)
    logger.info(
        "merged.wav criado: %s (%d Hz, %d amostras, offset mic=%.3fs sys=%.3fs)",
        out_path.name, target_sr, len(mixed_int16), mic_t0, sys_t0,
    )
    return out_path


def _to_mono_float(data: np.ndarray) -> np.ndarray:
    """Convert int16 (mono or stereo) to float32 mono in [-1, 1]."""
    f = data.astype(np.float32) / 32768.0
    if f.ndim == 2:
        f = f.mean(axis=1)
    return f


def _resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    import scipy.signal
    g = gcd(dst_rate, src_rate)
    return scipy.signal.resample_poly(data, dst_rate // g, src_rate // g).astype(np.float32)
