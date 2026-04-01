from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QVBoxLayout,
)

from ..config.settings import VALID_MODELS, Settings

# (display_name, whisper_code)
LANGUAGES = [
    ("Detecção automática", "auto"),
    ("Português",           "pt"),
    ("Inglês",              "en"),
    ("Espanhol",            "es"),
    ("Francês",             "fr"),
    ("Alemão",              "de"),
    ("Italiano",            "it"),
    ("Japonês",             "ja"),
    ("Coreano",             "ko"),
    ("Chinês",              "zh"),
    ("Russo",               "ru"),
    ("Árabe",               "ar"),
    ("Hindi",               "hi"),
]


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
        s.transcription.language = self._lang.currentData() or "auto"
        s.output.directory = self._out_dir.text().strip() or "recordings"
        s.diarization.enabled = self._diar_enabled.isChecked()
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

        self._lang = QComboBox()
        for display, code in LANGUAGES:
            self._lang.addItem(display, userData=code)
        trans_form.addRow("Idioma:", self._lang)

        layout.addWidget(trans_group)

        # ── Saída ──────────────────────────────────────────────────────
        out_group = QGroupBox("Saída")
        out_form = QFormLayout(out_group)

        self._out_dir = QLineEdit()
        out_form.addRow("Diretório de gravações:", self._out_dir)

        layout.addWidget(out_group)

        # ── Diarização ─────────────────────────────────────────────────
        diar_group = QGroupBox("Diarização (identificação de falantes)")
        diar_form = QFormLayout(diar_group)

        self._diar_enabled = QCheckBox("Ativar diarização")
        diar_form.addRow(self._diar_enabled)

        note = QLabel(
            'Usa o modelo público '
            '<a href="https://huggingface.co/freevoid/speaker-diarization-3.1">'
            "freevoid/speaker-diarization-3.1</a> — sem token necessário."
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
        codes = [code for _, code in LANGUAGES]
        lang_idx = codes.index(s.transcription.language) if s.transcription.language in codes else 0
        self._lang.setCurrentIndex(lang_idx)
        self._out_dir.setText(s.output.directory)
        self._diar_enabled.setChecked(s.diarization.enabled)
