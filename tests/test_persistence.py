from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from audio_recorder.persistence.database import (
    delete_session,
    get_db,
    get_segments,
    list_sessions,
    save_session,
    search_segments,
)


@dataclass
class _Seg:
    text: str
    start: float
    end: float
    source: str
    speaker: str | None = None


@pytest.fixture()
def db(tmp_path):
    conn = get_db(tmp_path / "test.db")
    yield conn
    conn.close()


def _sample_segments():
    return [
        _Seg("Olá mundo", 0.0, 1.5, "mic"),
        _Seg("Como vai você?", 2.0, 3.5, "system", "SPEAKER_00"),
        _Seg("Tudo bem por aqui", 4.0, 5.0, "mic"),
    ]


class TestSaveAndList:
    def test_save_returns_id(self, db):
        segs = _sample_segments()
        sid = save_session(db, Path("/tmp/sess1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        assert sid == 1

    def test_list_sessions_count(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        save_session(db, Path("/tmp/s2"), "2026-04-01T11:00:00", "2026-04-01T11:03:00", segs[:1])
        rows = list_sessions(db)
        assert len(rows) == 2

    def test_list_sessions_newest_first(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T09:00:00", "2026-04-01T09:05:00", segs)
        save_session(db, Path("/tmp/s2"), "2026-04-01T11:00:00", "2026-04-01T11:05:00", segs)
        rows = list_sessions(db)
        assert rows[0]["started_at"] > rows[1]["started_at"]

    def test_segment_count_in_list(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        rows = list_sessions(db)
        assert rows[0]["segment_count"] == 3

    def test_duration_stored(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        rows = list_sessions(db)
        assert rows[0]["duration_s"] == pytest.approx(5.0)


class TestGetSegments:
    def test_returns_ordered_by_start(self, db):
        segs = _sample_segments()
        sid = save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        result = get_segments(db, sid)
        starts = [r["start"] for r in result]
        assert starts == sorted(starts)

    def test_text_and_speaker_preserved(self, db):
        segs = _sample_segments()
        sid = save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        result = get_segments(db, sid)
        assert result[1]["text"] == "Como vai você?"
        assert result[1]["speaker"] == "SPEAKER_00"

    def test_empty_for_unknown_session(self, db):
        assert get_segments(db, 999) == []


class TestSearch:
    def test_fts_finds_match(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        results = search_segments(db, "mundo")
        assert len(results) == 1
        assert "mundo" in results[0]["text"]

    def test_fts_no_match(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        results = search_segments(db, "inexistente")
        assert results == []

    def test_fts_includes_session_metadata(self, db):
        segs = _sample_segments()
        save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        results = search_segments(db, "bem")
        assert "session_id" in results[0]
        assert "started_at" in results[0]


class TestDelete:
    def test_delete_removes_session(self, db):
        segs = _sample_segments()
        sid = save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        delete_session(db, sid)
        assert list_sessions(db) == []

    def test_delete_cascades_to_segments(self, db):
        segs = _sample_segments()
        sid = save_session(db, Path("/tmp/s1"), "2026-04-01T10:00:00", "2026-04-01T10:05:00", segs)
        delete_session(db, sid)
        assert get_segments(db, sid) == []

    def test_delete_nonexistent_is_noop(self, db):
        delete_session(db, 999)  # should not raise
