from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QVBoxLayout,
)

from ..config.settings import VALID_MODELS, Settings


class SettingsWindow(QDialog):
    """Modal dialog for editing application settings."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setFixedWidth(460)
        self._original = settings
        self._build_ui()
        self._load(settings)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_settings(self) -> Settings:
        s = deepcopy(self._original)
        s.transcription.model = self._model.currentText()
        s.transcription.language = self._lang.text().strip() or "auto"
        s.output.directory = self._out_dir.text().strip() or "recordings"
        s.output.formats = [
            fmt for fmt, cb in [("txt", self._fmt_txt), ("srt", self._fmt_srt), ("json", self._fmt_json)]
            if cb.isChecked()
        ]
        s.diarization.enabled = self._diar_enabled.isChecked()
        s.diarization.token = self._hf_token.text().strip()
        return s

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Transcrição ────────────────────────────────────────────────
        trans_group = QGroupBox("Transcrição")
        trans_form = QFormLayout(trans_group)

        self._model = QComboBox()
        self._model.addItems(sorted(VALID_MODELS))
        trans_form.addRow("Modelo Whisper:", self._model)

        self._lang = QLineEdit()
        self._lang.setPlaceholderText("auto")
        trans_form.addRow("Idioma:", self._lang)

        layout.addWidget(trans_group)

        # ── Saída ──────────────────────────────────────────────────────
        out_group = QGroupBox("Saída")
        out_form = QFormLayout(out_group)

        self._out_dir = QLineEdit()
        out_form.addRow("Diretório:", self._out_dir)

        fmt_row = QHBoxLayout()
        self._fmt_txt = QCheckBox("TXT")
        self._fmt_srt = QCheckBox("SRT")
        self._fmt_json = QCheckBox("JSON")
        for cb in (self._fmt_txt, self._fmt_srt, self._fmt_json):
            fmt_row.addWidget(cb)
        fmt_row.addStretch()
        out_form.addRow("Formatos:", fmt_row)

        layout.addWidget(out_group)

        # ── Diarização ─────────────────────────────────────────────────
        diar_group = QGroupBox("Diarização (identificação de falantes)")
        diar_form = QFormLayout(diar_group)

        self._diar_enabled = QCheckBox("Ativar diarização")
        diar_form.addRow(self._diar_enabled)

        self._hf_token = QLineEdit()
        self._hf_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._hf_token.setPlaceholderText("hf_…")
        diar_form.addRow("Token HuggingFace:", self._hf_token)

        note = QLabel(
            '<a href="https://huggingface.co/pyannote/speaker-diarization-3.1">'
            "Aceite os termos do modelo antes de usar.</a>"
        )
        note.setOpenExternalLinks(True)
        note.setWordWrap(True)
        diar_form.addRow(note)

        layout.addWidget(diar_group)

        # ── Botões ─────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self, s: Settings) -> None:
        idx = self._model.findText(s.transcription.model)
        self._model.setCurrentIndex(max(idx, 0))
        self._lang.setText(s.transcription.language)
        self._out_dir.setText(s.output.directory)
        self._fmt_txt.setChecked("txt" in s.output.formats)
        self._fmt_srt.setChecked("srt" in s.output.formats)
        self._fmt_json.setChecked("json" in s.output.formats)
        self._diar_enabled.setChecked(s.diarization.enabled)
        self._hf_token.setText(s.diarization.token)
