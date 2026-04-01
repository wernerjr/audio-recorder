from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..persistence.database import delete_session, get_db, get_segments, list_sessions
from .widgets.transcript_view import TranscriptView


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
        self.resize(960, 640)
        self._db_path = db_path
        self._sessions: list[dict] = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_search)

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(1.0)

        self._build_ui()
        self._connect_player()
        self._load_sessions()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setSpacing(8)

        # ── Left panel: session list ───────────────────────────────────
        left = QWidget()
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Sessões"))

        self._session_list = QListWidget()
        self._session_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self._session_list)

        self._delete_btn = QPushButton("Excluir sessão")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        left_layout.addWidget(self._delete_btn)

        root.addWidget(left)

        # ── Right panel: player + transcript ──────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Audio player controls
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

        right_layout.addLayout(player_row)

        # Search
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Digite para filtrar...")
        self._search_box.textChanged.connect(self._search_timer.start)
        search_row.addWidget(self._search_box)
        right_layout.addLayout(search_row)

        self._transcript = TranscriptView()
        self._transcript.setPlaceholderText("Selecione uma sessão para ver a transcrição.")
        right_layout.addWidget(self._transcript)

        root.addWidget(right)

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
        self._delete_btn.setEnabled(row >= 0)
        if row < 0:
            return

        session = self._sessions[row]
        session_id = session["id"]
        self._show_session(session_id)

        # Load audio if available
        merged_wav = session.get("merged_wav")
        if merged_wav and Path(merged_wav).exists():
            self._player.setSource(QUrl.fromLocalFile(merged_wav))
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
        self._load_sessions()
        self._delete_btn.setEnabled(False)

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
