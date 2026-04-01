from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT    NOT NULL,
    ended_at   TEXT,
    duration_s REAL,
    output_dir TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    start      REAL    NOT NULL,
    end        REAL    NOT NULL,
    source     TEXT    NOT NULL,
    speaker    TEXT,
    text       TEXT    NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    content=segments,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS segments_ai
AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad
AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


def get_db(path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database at *path*, apply schema, return connection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript(_DDL)
    db.commit()
    return db


def save_session(
    db: sqlite3.Connection,
    output_dir: Path,
    started_at: str,
    ended_at: str,
    segments: list[Any],
) -> int:
    """
    Persist one recording session and its merged segments.

    *segments* is a list of objects with attributes:
        text, start, end, source, speaker  (MergedSegment from merge/merger.py)

    Returns the new session id.
    """
    duration = segments[-1].end if segments else 0.0

    cur = db.execute(
        "INSERT INTO sessions (started_at, ended_at, duration_s, output_dir) VALUES (?,?,?,?)",
        (started_at, ended_at, duration, str(output_dir)),
    )
    session_id = cur.lastrowid

    db.executemany(
        "INSERT INTO segments (session_id, start, end, source, speaker, text) VALUES (?,?,?,?,?,?)",
        [
            (session_id, seg.start, seg.end, seg.source, getattr(seg, "speaker", None), seg.text)
            for seg in segments
        ],
    )
    db.commit()
    return session_id


def list_sessions(db: sqlite3.Connection) -> list[dict]:
    """Return all sessions ordered newest-first, including segment count."""
    rows = db.execute(
        """
        SELECT s.id, s.started_at, s.ended_at, s.duration_s, s.output_dir,
               COUNT(sg.id) AS segment_count
        FROM sessions s
        LEFT JOIN segments sg ON sg.session_id = s.id
        GROUP BY s.id
        ORDER BY s.started_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_segments(db: sqlite3.Connection, session_id: int) -> list[dict]:
    """Return all segments for *session_id* ordered by start time."""
    rows = db.execute(
        "SELECT start, end, source, speaker, text FROM segments WHERE session_id=? ORDER BY start",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def search_segments(db: sqlite3.Connection, query: str) -> list[dict]:
    """
    Full-text search across all segments.
    Returns matches with session metadata, ordered by session (newest first) then start.
    """
    rows = db.execute(
        """
        SELECT sg.session_id, sg.start, sg.end, sg.source, sg.speaker, sg.text,
               s.started_at, s.output_dir
        FROM segments_fts fts
        JOIN segments sg ON sg.id = fts.rowid
        JOIN sessions s  ON s.id  = sg.session_id
        WHERE segments_fts MATCH ?
        ORDER BY s.started_at DESC, sg.start
        """,
        (query,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_session(db: sqlite3.Connection, session_id: int) -> None:
    """Delete a session and all its segments (CASCADE handles the segments table)."""
    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    db.commit()
