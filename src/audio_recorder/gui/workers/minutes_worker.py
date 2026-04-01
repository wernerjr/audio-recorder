from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class MinutesWorker(QThread):
    """
    Generates meeting minutes from transcript segments off the GUI thread.

    Emits:
        progress(str)  — status messages for the UI
        finished(str)  — the generated minutes text
        error(str)     — error message if generation fails
    """

    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        segments: list[dict],
        model_id: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._segments = segments
        self._model_id = model_id

    def run(self) -> None:
        try:
            from ...summarization.engine import SummarizationEngine

            self.progress.emit(f"Carregando modelo '{self._model_id}'…")
            engine = SummarizationEngine(self._model_id)

            self.progress.emit("Gerando ata…")
            text = engine.summarize(self._segments)
            self.finished.emit(text)

        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")
