from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RecordingIndicator(QWidget):
    """
    Animated pulsing dot that signals recording status.
    When recording=True, pulses between bright and dim red.
    When recording=False, shows a static gray dot.
    """

    _DOT_RADIUS = 10
    _COLOR_ACTIVE_BRIGHT = QColor("#e74c3c")
    _COLOR_ACTIVE_DIM = QColor("#922b21")
    _COLOR_IDLE = QColor("#555e70")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self._recording = False
        self._pulse_lit = False

        self._timer = QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._toggle_pulse)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        self._pulse_lit = False
        if recording:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx = self._DOT_RADIUS + 8
        cy = h // 2
        r = self._DOT_RADIUS

        if self._recording:
            color = self._COLOR_ACTIVE_BRIGHT if self._pulse_lit else self._COLOR_ACTIVE_DIM
            text = "● REC"
            text_color = QColor("#e74c3c")
        else:
            color = self._COLOR_IDLE
            text = "● PARADO"
            text_color = QColor("#7f8c8d")

        # Dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Label
        painter.setPen(QPen(text_color))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(self._recording)
        painter.setFont(font)
        painter.drawText(cx + r + 8, cy + 5, text)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _toggle_pulse(self) -> None:
        self._pulse_lit = not self._pulse_lit
        self.update()
