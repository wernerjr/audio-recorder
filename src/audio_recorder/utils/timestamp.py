from __future__ import annotations


def format_ts(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm string."""
    total_ms = int(seconds * 1000)
    hours, total_ms = divmod(total_ms, 3_600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, ms = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def ts_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS.mmm string to seconds."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
