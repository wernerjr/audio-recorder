from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config.settings import VALID_MODELS
from ..persistence.database import (
    delete_minutes,
    delete_session,
    get_db,
    get_minutes,
    get_segments,
    list_sessions,
    replace_segments,
    save_minutes,
    update_minutes,
)
from ..summarization.engine import SummarizationEngine
from .widgets.transcript_view import TranscriptView

_MINUTES_MODEL = SummarizationEngine.DEFAULT_MODEL


@dataclass
class _SegmentRow:
    """Thin adapter so TranscriptView.append_result() works with DB dicts."""
    text: str
    start: float
    end: float
    source: str
    speaker: str | None


def _fmt_time(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


class HistoryWindow(QDialog):
    """Modal dialog showing past recording sessions and their transcripts."""

    def __init__(self, db_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Histórico de Gravações")
        self.resize(1020, 660)
        self._db_path = db_path
        self._sessions: list[dict] = []
        self._current_session: dict | None = None
        self._current_minutes_id: int | None = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_search)

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(1.0)

        self._retranscribe_worker = None
        self._minutes_worker = None

        self._build_ui()
        self._connect_player()
        self._load_sessions()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setSpacing(8)

        # ── Left panel: session list + actions ────────────────────────
        left = QWidget()
        left.setFixedWidth(270)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Sessões"))

        self._session_list = QListWidget()
        self._session_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self._session_list)

        self._retranscribe_btn = QPushButton("🔄  Retranscrever")
        self._retranscribe_btn.setEnabled(False)
        self._retranscribe_btn.setToolTip("Retranscrever com outro modelo Whisper")
        self._retranscribe_btn.clicked.connect(self._on_retranscribe)
        left_layout.addWidget(self._retranscribe_btn)

        self._delete_btn = QPushButton("🗑  Excluir sessão")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        left_layout.addWidget(self._delete_btn)

        self._action_status = QLabel("")
        self._action_status.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        self._action_status.setWordWrap(True)
        left_layout.addWidget(self._action_status)

        root.addWidget(left)

        # ── Right panel: tabs ─────────────────────────────────────────
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, stretch=1)

        self._tabs.addTab(self._build_transcript_tab(), "Transcrição")
        self._tabs.addTab(self._build_minutes_tab(), "Ata")

    def _build_transcript_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 4, 0, 0)

        # Player controls
        player_row = QHBoxLayout()
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(40)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._toggle_play)
        player_row.addWidget(self._play_btn)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setEnabled(False)
        self._seek_slider.sliderMoved.connect(self._on_seek)
        player_row.addWidget(self._seek_slider, stretch=1)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setFixedWidth(90)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        player_row.addWidget(self._time_label)
        layout.addLayout(player_row)

        # Search
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Digite para filtrar…")
        self._search_box.textChanged.connect(self._search_timer.start)
        search_row.addWidget(self._search_box)
        layout.addLayout(search_row)

        self._transcript = TranscriptView()
        self._transcript.setPlaceholderText("Selecione uma sessão para ver a transcrição.")
        layout.addWidget(self._transcript)

        return tab

    def _build_minutes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 4, 0, 0)

        btn_row = QHBoxLayout()
        self._generate_btn = QPushButton("✨  Gerar Ata")
        self._generate_btn.setEnabled(False)
        self._generate_btn.clicked.connect(self._on_generate_minutes)
        btn_row.addWidget(self._generate_btn)

        self._save_minutes_btn = QPushButton("💾  Salvar")
        self._save_minutes_btn.setEnabled(False)
        self._save_minutes_btn.clicked.connect(self._on_save_minutes)
        btn_row.addWidget(self._save_minutes_btn)

        self._delete_minutes_btn = QPushButton("🗑  Excluir Ata")
        self._delete_minutes_btn.setEnabled(False)
        self._delete_minutes_btn.clicked.connect(self._on_delete_minutes)
        btn_row.addWidget(self._delete_minutes_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._minutes_status = QLabel("")
        self._minutes_status.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(self._minutes_status)

        self._minutes_edit = QTextEdit()
        self._minutes_edit.setPlaceholderText(
            "A ata gerada aparecerá aqui. Você pode editá-la antes de salvar."
        )
        self._minutes_edit.setStyleSheet(
            "QTextEdit {"
            "  background-color: #1e2330; color: #dfe6e9;"
            "  border: 1px solid #2d3561; border-radius: 6px; padding: 6px;"
            "}"
        )
        layout.addWidget(self._minutes_edit)

        return tab

    def _connect_player(self) -> None:
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        self._session_list.clear()
        self._sessions = []

        if not self._db_path.exists():
            return

        db = get_db(self._db_path)
        try:
            self._sessions = list_sessions(db)
        finally:
            db.close()

        for s in self._sessions:
            duration = s.get("duration_s") or 0.0
            mins, secs = divmod(int(duration), 60)
            count = s.get("segment_count", 0)
            started = s["started_at"].replace("T", " ")[:16]
            has_audio = "🔊 " if s.get("merged_wav") else ""
            label = f"{has_audio}{started}  ({mins}:{secs:02d}, {count} seg.)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self._session_list.addItem(item)

    # ------------------------------------------------------------------
    # Slots — session list
    # ------------------------------------------------------------------

    def _on_session_selected(self, row: int) -> None:
        self._player.stop()
        has_session = row >= 0
        self._delete_btn.setEnabled(has_session)

        if not has_session:
            self._current_session = None
            self._retranscribe_btn.setEnabled(False)
            self._generate_btn.setEnabled(False)
            return

        session = self._sessions[row]
        self._current_session = session
        session_id = session["id"]

        has_audio = bool(session.get("merged_wav") and Path(session["merged_wav"]).exists())
        self._retranscribe_btn.setEnabled(has_audio)
        self._generate_btn.setEnabled(True)
        self._action_status.setText("")

        self._show_session(session_id)
        self._load_minutes_for_session(session_id)

        if has_audio:
            self._player.setSource(QUrl.fromLocalFile(session["merged_wav"]))
            self._play_btn.setEnabled(True)
            self._seek_slider.setEnabled(True)
        else:
            self._player.setSource(QUrl())
            self._play_btn.setEnabled(False)
            self._seek_slider.setEnabled(False)
            self._seek_slider.setValue(0)
            self._time_label.setText("0:00 / 0:00")

    def _show_session(self, session_id: int, filter_text: str = "") -> None:
        db = get_db(self._db_path)
        try:
            rows = get_segments(db, session_id)
        finally:
            db.close()

        self._transcript.clear_transcript()
        query = filter_text.strip().lower()
        for r in rows:
            if query and query not in r["text"].lower():
                continue
            self._transcript.append_result(
                _SegmentRow(
                    text=r["text"],
                    start=r["start"],
                    end=r["end"],
                    source=r["source"],
                    speaker=r.get("speaker"),
                )
            )

    def _load_minutes_for_session(self, session_id: int) -> None:
        db = get_db(self._db_path)
        try:
            minutes = get_minutes(db, session_id)
        finally:
            db.close()

        if minutes:
            self._current_minutes_id = minutes["id"]
            self._minutes_edit.setPlainText(minutes["content"])
            self._minutes_status.setText(
                f"Gerado em {minutes['created_at'][:16].replace('T',' ')} · {minutes['model_id']}"
            )
            self._save_minutes_btn.setEnabled(True)
            self._delete_minutes_btn.setEnabled(True)
        else:
            self._current_minutes_id = None
            self._minutes_edit.clear()
            self._minutes_status.setText("")
            self._save_minutes_btn.setEnabled(False)
            self._delete_minutes_btn.setEnabled(False)

    def _apply_search(self) -> None:
        item = self._session_list.currentItem()
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        self._show_session(session_id, self._search_box.text())

    def _on_delete(self) -> None:
        item = self._session_list.currentItem()
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Excluir sessão",
            "Remover esta sessão do histórico? Os arquivos de áudio não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._player.stop()
        db = get_db(self._db_path)
        try:
            delete_session(db, session_id)
        finally:
            db.close()

        self._transcript.clear_transcript()
        self._minutes_edit.clear()
        self._load_sessions()
        self._delete_btn.setEnabled(False)
        self._retranscribe_btn.setEnabled(False)
        self._generate_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots — retranscription
    # ------------------------------------------------------------------

    def _on_retranscribe(self) -> None:
        if self._current_session is None:
            return

        models = sorted(VALID_MODELS)
        model, ok = QInputDialog.getItem(
            self,
            "Retranscrever",
            "Escolha o modelo Whisper:",
            models,
            models.index("small") if "small" in models else 0,
            False,
        )
        if not ok:
            return

        from .workers.retranscribe_worker import RetranscribeWorker

        self._set_busy(True)
        self._action_status.setText(f"Retranscrevendo com '{model}'…")

        self._retranscribe_worker = RetranscribeWorker(
            self._current_session["merged_wav"], model, parent=self
        )
        self._retranscribe_worker.progress.connect(self._action_status.setText)
        self._retranscribe_worker.finished.connect(self._on_retranscribe_done)
        self._retranscribe_worker.error.connect(self._on_action_error)
        self._retranscribe_worker.start()

    def _on_retranscribe_done(self, segments: list) -> None:
        self._set_busy(False)
        session_id = self._current_session["id"]
        db = get_db(self._db_path)
        try:
            replace_segments(db, session_id, segments)
        finally:
            db.close()

        self._action_status.setText("Retranscrição concluída.")
        self._show_session(session_id)
        self._load_sessions()  # refresh segment count

    # ------------------------------------------------------------------
    # Slots — meeting minutes
    # ------------------------------------------------------------------

    def _on_generate_minutes(self) -> None:
        if self._current_session is None:
            return

        session_id = self._current_session["id"]
        db = get_db(self._db_path)
        try:
            segments = get_segments(db, session_id)
        finally:
            db.close()

        if not segments:
            QMessageBox.information(self, "Ata", "Nenhum segmento de transcrição encontrado.")
            return

        from .workers.minutes_worker import MinutesWorker

        self._set_busy(True)
        self._minutes_status.setText(f"Gerando ata com '{_MINUTES_MODEL}'…")

        self._minutes_worker = MinutesWorker(segments, _MINUTES_MODEL, parent=self)
        self._minutes_worker.progress.connect(self._minutes_status.setText)
        self._minutes_worker.finished.connect(self._on_minutes_generated)
        self._minutes_worker.error.connect(self._on_action_error)
        self._minutes_worker.start()

    def _on_minutes_generated(self, text: str) -> None:
        self._set_busy(False)
        self._minutes_edit.setPlainText(text)
        self._minutes_status.setText("Ata gerada — revise e clique em Salvar.")
        self._save_minutes_btn.setEnabled(True)
        self._tabs.setCurrentIndex(1)  # switch to Ata tab

    def _on_save_minutes(self) -> None:
        if self._current_session is None:
            return
        content = self._minutes_edit.toPlainText().strip()
        if not content:
            return

        session_id = self._current_session["id"]
        db = get_db(self._db_path)
        try:
            if self._current_minutes_id is not None:
                update_minutes(db, self._current_minutes_id, content)
            else:
                self._current_minutes_id = save_minutes(db, session_id, content, _MINUTES_MODEL)
        finally:
            db.close()

        self._minutes_status.setText("Ata salva.")
        self._delete_minutes_btn.setEnabled(True)

    def _on_delete_minutes(self) -> None:
        if self._current_minutes_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Excluir Ata",
            "Remover a ata desta sessão?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db(self._db_path)
        try:
            delete_minutes(db, self._current_minutes_id)
        finally:
            db.close()

        self._current_minutes_id = None
        self._minutes_edit.clear()
        self._minutes_status.setText("")
        self._save_minutes_btn.setEnabled(False)
        self._delete_minutes_btn.setEnabled(False)

    def _on_action_error(self, msg: str) -> None:
        self._set_busy(False)
        self._action_status.setText("Erro — veja detalhes abaixo.")
        QMessageBox.critical(self, "Erro", msg)

    def _set_busy(self, busy: bool) -> None:
        self._retranscribe_btn.setEnabled(not busy)
        self._generate_btn.setEnabled(not busy)
        self._delete_btn.setEnabled(not busy)
        self._save_minutes_btn.setEnabled(not busy)
        self._delete_minutes_btn.setEnabled(not busy)

    # ------------------------------------------------------------------
    # Slots — audio player
    # ------------------------------------------------------------------

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_seek(self, value: int) -> None:
        self._player.setPosition(value)

    def _on_position_changed(self, pos_ms: int) -> None:
        duration = self._player.duration()
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(pos_ms)
        self._seek_slider.blockSignals(False)
        self._time_label.setText(f"{_fmt_time(pos_ms)} / {_fmt_time(duration)}")
        self._transcript.highlight_at(pos_ms / 1000.0)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._seek_slider.setRange(0, duration_ms)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._player.stop()
        super().closeEvent(event)
