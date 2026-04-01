import pytest

from audio_recorder.merge.merger import Merger, MergedSegment, _deduplicate
from audio_recorder.transcription.segment import TranscriptResult


def _result(text: str, start: float, end: float, source: str = "mic") -> TranscriptResult:
    return TranscriptResult(text=text, start=start, end=end, source=source)


def _seg(text: str, start: float, end: float, source: str = "mic") -> MergedSegment:
    return MergedSegment(text=text, start=start, end=end, source=source)


class TestMerger:
    def test_merge_sorts_by_start(self):
        mic = [_result("B", 2.0, 3.0), _result("A", 0.0, 1.0)]
        sys: list[TranscriptResult] = []
        segments = Merger().merge(mic, sys)
        assert [s.text for s in segments] == ["A", "B"]

    def test_merge_combines_both_sources(self):
        mic = [_result("mic text", 0.0, 1.0, "mic")]
        sys = [_result("sys text", 1.5, 2.5, "system")]
        segments = Merger().merge(mic, sys)
        assert len(segments) == 2
        assert segments[0].source == "mic"
        assert segments[1].source == "system"

    def test_merge_empty_inputs(self):
        assert Merger().merge([], []) == []


class TestDeduplicate:
    def test_removes_identical_overlapping(self):
        segs = [
            _seg("hello world", 0.0, 1.0),
            _seg("hello world", 0.3, 1.3),   # overlaps + same text
        ]
        result = _deduplicate(segs)
        assert len(result) == 1

    def test_keeps_similar_but_non_overlapping(self):
        segs = [
            _seg("hello world", 0.0, 1.0),
            _seg("hello world", 2.0, 3.0),   # same text but no temporal overlap
        ]
        result = _deduplicate(segs)
        assert len(result) == 2

    def test_keeps_different_overlapping(self):
        segs = [
            _seg("hello world", 0.0, 1.0),
            _seg("completely different text", 0.3, 1.3),   # overlaps but different text
        ]
        result = _deduplicate(segs)
        assert len(result) == 2

    def test_empty_input(self):
        assert _deduplicate([]) == []

    def test_single_segment(self):
        segs = [_seg("only one", 0.0, 1.0)]
        assert _deduplicate(segs) == segs
