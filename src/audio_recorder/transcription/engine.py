from __future__ import annotations

from math import gcd

import numpy as np

from .segment import AudioSegment, TranscriptResult

WHISPER_SAMPLE_RATE = 16000


def _prepare_audio(segment: AudioSegment) -> np.ndarray:
    """Convert AudioSegment bytes to float32 mono at 16kHz for Whisper."""
    import scipy.signal

    audio = np.frombuffer(segment.data, dtype=np.int16).astype(np.float32) / 32768.0
    if segment.channels > 1:
        audio = audio.reshape(-1, segment.channels).mean(axis=1)
    if segment.sample_rate != WHISPER_SAMPLE_RATE:
        g = gcd(WHISPER_SAMPLE_RATE, segment.sample_rate)
        audio = scipy.signal.resample_poly(
            audio, WHISPER_SAMPLE_RATE // g, segment.sample_rate // g
        ).astype(np.float32)
    return audio


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


class WhisperEngine:
    """
    Wraps faster-whisper for transcription.
    Model is loaded once and reused across segments.
    """

    def __init__(self, model_name: str = "small", language: str = "auto") -> None:
        from faster_whisper import WhisperModel

        device = "cuda" if _cuda_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self._language: str | None = None if language == "auto" else language

    def transcribe(self, segment: AudioSegment) -> list[TranscriptResult]:
        """Transcribe a single AudioSegment and return a list of TranscriptResults."""
        audio = _prepare_audio(segment)
        if len(audio) == 0:
            return []

        segments, _ = self._model.transcribe(
            audio,
            language=self._language,
            vad_filter=False,   # VAD already done upstream
            word_timestamps=False,
        )

        results = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            results.append(TranscriptResult(
                text=text,
                start=segment.start + seg.start,
                end=segment.start + seg.end,
                source=segment.source,
            ))
        return results
