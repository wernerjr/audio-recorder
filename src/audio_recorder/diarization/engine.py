from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiarizationSegment:
    start: float    # seconds
    end: float      # seconds
    speaker: str    # e.g. "SPEAKER_00"


class DiarizationEngine:
    """
    Wraps pyannote-audio speaker diarization pipeline.

    Requires a HuggingFace token with access to:
      pyannote/speaker-diarization-3.1

    Accept the model conditions at:
      https://huggingface.co/pyannote/speaker-diarization-3.1

    Usage:
        engine = DiarizationEngine(token="hf_...")
        segments = engine.diarize(Path("microfone.wav"))
    """

    MODEL_ID = "pyannote/speaker-diarization-3.1"

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError(
                "Token HuggingFace obrigatório para diarização. "
                "Defina 'diarization.token' no config.toml ou a variável "
                "de ambiente HUGGINGFACE_TOKEN."
            )
        self._token = token
        self._pipeline = None  # lazy load

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        from pyannote.audio import Pipeline

        self._pipeline = Pipeline.from_pretrained(
            self.MODEL_ID,
            use_auth_token=self._token,
        )

    def diarize(self, audio_path: Path) -> list[DiarizationSegment]:
        """Run diarization on a WAV file and return speaker segments."""
        self._load()
        assert self._pipeline is not None

        diarization = self._pipeline(str(audio_path))
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(DiarizationSegment(
                start=turn.start,
                end=turn.end,
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
