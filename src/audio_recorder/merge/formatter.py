from __future__ import annotations

import json
from pathlib import Path

from .merger import MergedSegment
from ..utils.timestamp import format_ts


def write_txt(segments: list[MergedSegment], path: Path) -> None:
    """Write merged transcript in plain-text format."""
    with open(path, "w", encoding="utf-8") as f:
        for seg in segments:
            label = _label(seg)
            f.write(f"[{format_ts(seg.start)} --> {format_ts(seg.end)}] {label}{seg.text}\n")


def write_srt(segments: list[MergedSegment], path: Path) -> None:
    """Write merged transcript in SRT subtitle format."""
    with open(path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_srt_ts(seg.start)} --> {_srt_ts(seg.end)}\n")
            f.write(f"{_label(seg)}{seg.text}\n\n")


def write_json(segments: list[MergedSegment], path: Path) -> None:
    """Write merged transcript as a JSON array."""
    data = [
        {
            "start": seg.start,
            "end": seg.end,
            "source": seg.source,
            "speaker": seg.speaker,
            "text": seg.text,
        }
        for seg in segments
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_all(
    segments: list[MergedSegment],
    base_path: Path,
    formats: list[str],
) -> list[Path]:
    """Write output in all requested formats. Returns list of created paths."""
    writers = {"txt": write_txt, "srt": write_srt, "json": write_json}
    created = []
    for fmt in formats:
        if fmt not in writers:
            continue
        out = base_path.with_suffix(f".{fmt}")
        writers[fmt](segments, out)
        created.append(out)
    return created


def _label(seg: MergedSegment) -> str:
    parts = [seg.source.upper()]
    if seg.speaker:
        parts.append(seg.speaker)
    return "[" + "][".join(parts) + "] "


def _srt_ts(seconds: float) -> str:
    """SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
