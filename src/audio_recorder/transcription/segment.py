from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioSegment:
    """A speech segment emitted by VADWorker, ready for transcription."""
    data: bytes        # PCM Int16, original sample rate
    sample_rate: int
    channels: int
    start: float       # session-relative seconds
    end: float
    source: str        # "mic" | "system"


@dataclass
class TranscriptResult:
    """A transcribed text segment produced by WhisperEngine."""
    text: str
    start: float       # session-relative seconds
    end: float
    source: str        # "mic" | "system"
    speaker: str | None = None  # filled later by diarization
