from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

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

        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_transcript(self) -> None:
        self.clear()


def _write(cursor: QTextCursor, text: str, color: str, bold: bool = False) -> None:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(700)
    else:
        fmt.setFontWeight(400)
    cursor.setCharFormat(fmt)
    cursor.insertText(text)
