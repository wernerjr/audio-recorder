import json
from pathlib import Path

import pytest

from audio_recorder.merge.formatter import write_json, write_srt, write_txt, _srt_ts
from audio_recorder.merge.merger import MergedSegment


SEGMENTS = [
    MergedSegment(text="Olá mundo", start=0.0, end=1.5, source="mic"),
    MergedSegment(text="Como vai?", start=2.0, end=3.0, source="system", speaker="SPEAKER_00"),
]


class TestWriteTxt:
    def test_creates_file(self, tmp_path: Path):
        out = tmp_path / "transcript.txt"
        write_txt(SEGMENTS, out)
        assert out.exists()

    def test_contains_text(self, tmp_path: Path):
        out = tmp_path / "transcript.txt"
        write_txt(SEGMENTS, out)
        content = out.read_text(encoding="utf-8")
        assert "Olá mundo" in content
        assert "Como vai?" in content

    def test_contains_source_label(self, tmp_path: Path):
        out = tmp_path / "transcript.txt"
        write_txt(SEGMENTS, out)
        content = out.read_text(encoding="utf-8")
        assert "[MIC]" in content
        assert "[SYSTEM]" in content

    def test_contains_speaker_label(self, tmp_path: Path):
        out = tmp_path / "transcript.txt"
        write_txt(SEGMENTS, out)
        content = out.read_text(encoding="utf-8")
        assert "SPEAKER_00" in content


class TestWriteSrt:
    def test_creates_file(self, tmp_path: Path):
        out = tmp_path / "transcript.srt"
        write_srt(SEGMENTS, out)
        assert out.exists()

    def test_srt_format(self, tmp_path: Path):
        out = tmp_path / "transcript.srt"
        write_srt(SEGMENTS, out)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "1"           # sequence number
        assert "-->" in lines[1]         # timestamp line
        assert "Olá mundo" in lines[2]   # text line

    def test_srt_timestamp_format(self):
        assert _srt_ts(0.0) == "00:00:00,000"
        assert _srt_ts(3661.5) == "01:01:01,500"


class TestWriteJson:
    def test_creates_valid_json(self, tmp_path: Path):
        out = tmp_path / "transcript.json"
        write_json(SEGMENTS, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2

    def test_json_fields(self, tmp_path: Path):
        out = tmp_path / "transcript.json"
        write_json(SEGMENTS, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data[0]["text"] == "Olá mundo"
        assert data[0]["source"] == "mic"
        assert data[0]["start"] == pytest.approx(0.0)
        assert data[1]["speaker"] == "SPEAKER_00"
