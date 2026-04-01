from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiarizationSegment:
    start: float    # seconds
    end: float      # seconds
    speaker: str    # e.g. "SPEAKER_00"


class DiarizationEngine:
    """
    Wraps simple-diarizer for speaker diarization.

    Uses speechbrain/spkrec-ecapa-voxceleb embeddings — no token required.

    Usage:
        engine = DiarizationEngine()
        segments = engine.diarize(Path("microfone.wav"))
    """

    def __init__(self) -> None:
        self._diarizer = None  # lazy load

    def _load(self) -> None:
        if self._diarizer is not None:
            return
        from simple_diarizer.diarizer import Diarizer
        logger.info("Carregando modelo de diarização (ECAPA-TDNN)…")
        self._diarizer = Diarizer(embed_model="ecapa", cluster_method="sc")
        logger.info("Modelo de diarização carregado.")

    def diarize(self, audio_path: Path) -> list[DiarizationSegment]:
        """Run diarization on a WAV file and return speaker segments."""
        self._load()
        assert self._diarizer is not None

        logger.info("Diarizando: %s", audio_path)
        raw = self._diarizer.diarize(str(audio_path), num_speakers=None)

        segments = []
        for seg in raw:
            speaker = f"SPEAKER_{int(seg['label']):02d}"
            segments.append(DiarizationSegment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                speaker=speaker,
            ))
        return segments

    def assign_speakers(
        self,
        results: list,
        diarization: list[DiarizationSegment],
    ) -> list:
        """
        Enrich TranscriptResult list with speaker labels using best-overlap matching.
        Returns a new list with speaker fields filled in.
        """
        import copy
        enriched = copy.deepcopy(results)
        for result in enriched:
            best_speaker = _best_overlap(result.start, result.end, diarization)
            if best_speaker:
                result.speaker = best_speaker
        return enriched


def _best_overlap(
    start: float,
    end: float,
    diarization: list[DiarizationSegment],
) -> str | None:
    """Return the speaker with the most overlap with the given time range."""
    best_speaker: str | None = None
    best_overlap = 0.0
    for seg in diarization:
        overlap = min(end, seg.end) - max(start, seg.start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = seg.speaker
    return best_speaker
