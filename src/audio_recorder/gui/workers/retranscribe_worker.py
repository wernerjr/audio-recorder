from __future__ import annotations

import wave

from PySide6.QtCore import QThread, Signal


class RetranscribeWorker(QThread):
    """
    Transcribes merged.wav with a chosen Whisper model off the GUI thread.

    Emits:
        progress(str)   — status messages for the UI
        finished(list)  — list[dict] of {start, end, source, speaker, text}
        error(str)      — error message if transcription fails
    """

    progress = Signal(str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        merged_wav: str,
        model_name: str,
        language: str = "auto",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._merged_wav = merged_wav
        self._model_name = model_name
        self._language = language

    def run(self) -> None:
        try:
            from ...transcription.engine import WhisperEngine
            from ...transcription.segment import AudioSegment

            self.progress.emit(f"Carregando modelo '{self._model_name}'…")

            with wave.open(self._merged_wav, "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                data = wf.readframes(wf.getnframes())

            duration = len(data) / (sample_rate * channels * 2)
            segment = AudioSegment(
                data=data,
                sample_rate=sample_rate,
                channels=channels,
                start=0.0,
                end=duration,
                source="merged",
            )

            self.progress.emit("Transcrevendo…")
            engine = WhisperEngine(self._model_name, self._language)
            results = engine.transcribe(segment)

            segments = [
                {
                    "start": r.start,
                    "end": r.end,
                    "source": r.source,
                    "speaker": getattr(r, "speaker", None),
                    "text": r.text,
                }
                for r in results
            ]
            self.finished.emit(segments)

        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")
