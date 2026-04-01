from __future__ import annotations

import queue
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config.settings import Settings, load_settings
from ..session.session import RecordingSession, session_output_dir
from ..transcription.segment import TranscriptResult
from .widgets.transcript_view import TranscriptView
from .widgets.waveform import RecordingIndicator

_CONFIG_PATH = Path("config.toml")


class _StopWorker(QThread):
    """Runs session.stop() + merge_and_save() in a background thread."""

    finished = Signal(list)   # list[Path]
    failed = Signal(str)

    def __init__(
        self,
        session: RecordingSession,
        results: list[TranscriptResult],
        diarization_settings,
    ) -> None:
        super().__init__()
        self._session = session
        self._results = list(results)
        self._diar = diarization_settings

    def run(self) -> None:
        try:
            self._session.stop()

            # Drain any remaining results produced during shutdown
            while True:
                try:
                    r = self._session.result_queue.get_nowait()
                    self._results.append(r)
                except queue.Empty:
                    break

            diar_segments = None
            if self._diar.enabled and self._diar.token:
                from ..diarization.engine import DiarizationEngine
                engine = DiarizationEngine(self._diar.token)
                mic_wav = self._session._output_dir / "microfone.wav"
                if mic_wav.exists():
                    diar_segments = engine.diarize(mic_wav)

            files = self._session.merge_and_save(self._results, diar_segments)
            self.finished.emit(files)

        except Exception as exc:
            import traceback
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self._session: RecordingSession | None = None
        self._results: list[TranscriptResult] = []
        self._elapsed: int = 0
        self._settings: Settings = self._load_settings()
        self._stop_worker: _StopWorker | None = None

        self._build_ui()
        self._build_timers()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("Audio Recorder")
        self.setMinimumSize(760, 540)
        self.setStyleSheet(
            "QMainWindow, QWidget { background-color: #141922; color: #dfe6e9; }"
            "QPushButton {"
            "  background-color: #2d3561; color: #dfe6e9;"
            "  border: none; border-radius: 5px; padding: 6px 14px;"
            "}"
            "QPushButton:hover { background-color: #3d4a7a; }"
            "QPushButton:disabled { background-color: #1e2330; color: #555e70; }"
            "QPushButton#recordBtn {"
            "  background-color: #922b21; font-weight: bold; font-size: 13px;"
            "  padding: 8px 20px;"
            "}"
            "QPushButton#recordBtn:hover { background-color: #c0392b; }"
            "QPushButton#recordBtn[recording='true'] {"
            "  background-color: #1a5276;"
            "}"
            "QPushButton#recordBtn[recording='true']:hover { background-color: #2471a3; }"
            "QGroupBox { border: 1px solid #2d3561; border-radius: 5px; margin-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Header ──────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Audio Recorder")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        settings_btn = QPushButton("⚙  Configurações")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(settings_btn)
        root.addLayout(header)

        # ── Recording indicator ─────────────────────────────────────────
        self._indicator = RecordingIndicator()
        root.addWidget(self._indicator)

        # ── Transcript view ─────────────────────────────────────────────
        self._transcript = TranscriptView()
        root.addWidget(self._transcript, stretch=1)

        # ── Controls ────────────────────────────────────────────────────
        controls = QHBoxLayout()
        self._status_lbl = QLabel("Pronto para gravar")
        self._status_lbl.setStyleSheet("color: #7f8c8d; font-size: 12px;")

        self._record_btn = QPushButton("⬤  Gravar")
        self._record_btn.setObjectName("recordBtn")
        self._record_btn.setFixedWidth(140)
        self._record_btn.clicked.connect(self._toggle_recording)

        controls.addWidget(self._status_lbl)
        controls.addStretch()
        controls.addWidget(self._record_btn)
        root.addLayout(controls)

    def _build_timers(self) -> None:
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._drain_results)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def _toggle_recording(self) -> None:
        if self._session is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        output_dir = session_output_dir(self._settings.output.directory)
        self._session = RecordingSession(self._settings, output_dir)
        self._results = []
        self._elapsed = 0

        try:
            self._session.start()
        except Exception as exc:
            self._session = None
            QMessageBox.critical(
                self, "Erro ao iniciar gravação",
                f"{exc}\n\nDica: verifique os dispositivos com 'audio-recorder devices'.",
            )
            return

        self._poll_timer.start()
        self._elapsed_timer.start()
        self._indicator.set_recording(True)
        self._record_btn.setText("■  Parar")
        self._record_btn.setProperty("recording", "true")
        self._record_btn.style().unpolish(self._record_btn)
        self._record_btn.style().polish(self._record_btn)
        self._status_lbl.setText(f"Gravando…  sessão: {output_dir.name}")
        self.statusBar().showMessage(str(output_dir))

    def _stop_recording(self) -> None:
        self._poll_timer.stop()
        self._elapsed_timer.stop()
        self._record_btn.setEnabled(False)
        self._indicator.set_recording(False)
        self._status_lbl.setText("Encerrando workers e gerando transcrição…")

        self._stop_worker = _StopWorker(
            self._session,       # type: ignore[arg-type]
            self._results,
            self._settings.diarization,
        )
        self._stop_worker.finished.connect(self._on_stop_finished)
        self._stop_worker.failed.connect(self._on_stop_failed)
        self._stop_worker.start()

    def _on_stop_finished(self, files: list) -> None:
        self._session = None
        self._drain_results()  # final flush
        self._record_btn.setEnabled(True)
        self._record_btn.setText("⬤  Gravar")
        self._record_btn.setProperty("recording", "false")
        self._record_btn.style().unpolish(self._record_btn)
        self._record_btn.style().polish(self._record_btn)
        self._status_lbl.setText(f"Concluído — {len(files)} arquivo(s) gerado(s)")
        self.statusBar().showMessage(
            "  ".join(str(f) for f in files) if files else "Nenhum resultado."
        )

    def _on_stop_failed(self, error: str) -> None:
        self._session = None
        self._record_btn.setEnabled(True)
        self._record_btn.setText("⬤  Gravar")
        self._status_lbl.setText("Erro")
        QMessageBox.critical(self, "Erro ao encerrar sessão", error)

    # ------------------------------------------------------------------
    # Periodic callbacks
    # ------------------------------------------------------------------

    def _drain_results(self) -> None:
        if self._session is None:
            return
        for _ in range(20):  # max 20 per tick to keep UI responsive
            try:
                result = self._session.result_queue.get_nowait()
                self._results.append(result)
                self._transcript.append_result(result)
            except queue.Empty:
                break

    def _tick_elapsed(self) -> None:
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self._status_lbl.setText(f"Gravando…  {m:02d}:{s:02d}")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        from .settings_window import SettingsWindow
        win = SettingsWindow(self._settings, parent=self)
        if win.exec():
            self._settings = win.get_settings()

    def _load_settings(self) -> Settings:
        config_path = _CONFIG_PATH if _CONFIG_PATH.exists() else None
        try:
            return load_settings(config_path)
        except ValueError as exc:
            QMessageBox.warning(None, "Configuração inválida", str(exc))  # type: ignore[call-overload]
            return load_settings(None)
