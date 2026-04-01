from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

_HIGHLIGHT_BG = "#2d3561"
_NORMAL_BG = "#1e2330"

_SOURCE_COLORS = {
    "mic": "#5dade2",
    "system": "#58d68d",
    "file": "#f0b27a",
}


class TranscriptView(QTextEdit):
    """Read-only text area that displays TranscriptResults with colored labels."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        # (start_sec, end_sec, char_pos) — one entry per segment appended
        self._segment_anchors: list[tuple[float, float, int]] = []
        self._highlighted_anchor: int | None = None  # index into _segment_anchors
        self.setFont(QFont("Consolas", 10))
        self.setPlaceholderText("A transcrição aparecerá aqui durante a gravação...")
        self.setStyleSheet(
            "QTextEdit {"
            "  background-color: #1e2330;"
            "  color: #dfe6e9;"
            "  border: 1px solid #2d3561;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "}"
        )

    def append_result(self, result: object) -> None:
        from ...utils.timestamp import format_ts

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        anchor_pos = cursor.position()

        # Timestamp — gray
        _write(cursor, f"[{format_ts(result.start)}] ", "#7f8c8d")  # type: ignore[attr-defined]

        # Source + speaker label — colored
        label = f"[{result.source.upper()}]"  # type: ignore[attr-defined]
        if result.speaker:  # type: ignore[attr-defined]
            label += f"[{result.speaker}]"  # type: ignore[attr-defined]
        color = _SOURCE_COLORS.get(result.source, "#bdc3c7")  # type: ignore[attr-defined]
        _write(cursor, label + " ", color, bold=True)

        # Text — near-white
        _write(cursor, result.text + "\n", "#ecf0f1")  # type: ignore[attr-defined]

        self._segment_anchors.append((result.start, result.end, anchor_pos))  # type: ignore[attr-defined]
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def highlight_at(self, position_sec: float) -> None:
        """Highlight the segment active at *position_sec*; scroll it into view."""
        if not self._segment_anchors:
            return

        # Find the segment whose time range contains position_sec
        idx = None
        for i, (start, end, _) in enumerate(self._segment_anchors):
            if start <= position_sec < end:
                idx = i
                break
        # Fallback: last segment that started before position
        if idx is None:
            for i, (start, _, _) in enumerate(self._segment_anchors):
                if start <= position_sec:
                    idx = i

        if idx is None or idx == self._highlighted_anchor:
            return

        doc = self.document()

        # Clear previous highlight
        if self._highlighted_anchor is not None:
            prev = self._highlighted_anchor
            _, _, prev_pos = self._segment_anchors[prev]
            next_pos = (
                self._segment_anchors[prev + 1][2]
                if prev + 1 < len(self._segment_anchors)
                else doc.characterCount()
            )
            _set_bg(doc, prev_pos, next_pos - prev_pos, _NORMAL_BG)

        # Apply new highlight
        _, _, cur_pos = self._segment_anchors[idx]
        next_pos = (
            self._segment_anchors[idx + 1][2]
            if idx + 1 < len(self._segment_anchors)
            else doc.characterCount()
        )
        _set_bg(doc, cur_pos, next_pos - cur_pos, _HIGHLIGHT_BG)

        self._highlighted_anchor = idx

        # Scroll to the highlighted line
        cursor = QTextCursor(doc)
        cursor.setPosition(cur_pos)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_transcript(self) -> None:
        self._segment_anchors.clear()
        self._highlighted_anchor = None
        self.clear()


def _set_bg(doc, pos: int, length: int, color: str) -> None:
    """Apply background color to a character range in *doc*."""
    cursor = QTextCursor(doc)
    cursor.setPosition(pos)
    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, length)
    fmt = QTextCharFormat()
    fmt.setBackground(QColor(color))
    cursor.mergeCharFormat(fmt)


def _write(cursor: QTextCursor, text: str, color: str, bold: bool = False) -> None:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(700)
    else:
        fmt.setFontWeight(400)
    cursor.setCharFormat(fmt)
    cursor.insertText(text)
