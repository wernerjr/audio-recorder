from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from ..transcription.segment import TranscriptResult

DEDUP_TEXT_RATIO = 0.8    # minimum similarity to consider duplicate
DEDUP_OVERLAP_SEC = 0.2   # minimum temporal overlap (seconds) to consider duplicate


@dataclass
class MergedSegment:
    text: str
    start: float
    end: float
    source: str           # "mic" | "system"
    speaker: str | None = None


class Merger:
    """
    Merges TranscriptResult lists from mic and system channels into a
    single chronologically sorted list, removing near-duplicate segments.
    """

    def merge(
        self,
        mic_results: list[TranscriptResult],
        sys_results: list[TranscriptResult],
        diarization: list | None = None,
    ) -> list[MergedSegment]:
        combined = [_to_merged(r) for r in mic_results + sys_results]
        combined.sort(key=lambda s: s.start)
        deduped = _deduplicate(combined)

        if diarization:
            deduped = _assign_speakers(deduped, diarization)

        return deduped


def _to_merged(result: TranscriptResult) -> MergedSegment:
    return MergedSegment(
        text=result.text,
        start=result.start,
        end=result.end,
        source=result.source,
        speaker=result.speaker,
    )


def _deduplicate(segments: list[MergedSegment]) -> list[MergedSegment]:
    """Remove segments that are both temporally overlapping and textually similar."""
    if not segments:
        return segments

    result: list[MergedSegment] = [segments[0]]
    for seg in segments[1:]:
        prev = result[-1]
        temporal_overlap = min(prev.end, seg.end) - max(prev.start, seg.start)
        if temporal_overlap >= DEDUP_OVERLAP_SEC:
            ratio = SequenceMatcher(None, prev.text, seg.text).ratio()
            if ratio >= DEDUP_TEXT_RATIO:
                continue  # skip duplicate
        result.append(seg)

    return result


def _assign_speakers(
    segments: list[MergedSegment],
    diarization: list,
) -> list[MergedSegment]:
    from ..diarization.engine import _best_overlap
    for seg in segments:
        speaker = _best_overlap(seg.start, seg.end, diarization)
        if speaker:
            seg.speaker = speaker
    return segments
