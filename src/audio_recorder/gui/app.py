from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def run() -> None:
    """Launch the Audio Recorder GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Audio Recorder")
    app.setApplicationDisplayName("Audio Recorder")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
