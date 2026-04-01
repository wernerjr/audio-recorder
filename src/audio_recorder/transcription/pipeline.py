from __future__ import annotations

import logging
import queue
import threading

from .engine import WhisperEngine
from .segment import AudioSegment, TranscriptResult

logger = logging.getLogger(__name__)


class TranscriptionWorker(threading.Thread):
    """
    Reads AudioSegments from segment_queue, transcribes each one using
    WhisperEngine, and puts TranscriptResults into result_queue.

    One instance handles one audio source (mic or system). Run two in
    parallel for dual-channel recording.
    """

    def __init__(
        self,
        segment_queue: queue.Queue[AudioSegment],
        result_queue: queue.Queue[TranscriptResult],
        stop_event: threading.Event,
        model_name: str = "small",
        language: str = "auto",
        source: str = "",
    ) -> None:
        super().__init__(name=f"transcription-{source}", daemon=True)
        self._seg_q = segment_queue
        self._result_q = result_queue
        self._stop = stop_event
        self._model_name = model_name
        self._language = language

    def run(self) -> None:
        engine = WhisperEngine(self._model_name, self._language)

        while not self._stop.is_set() or not self._seg_q.empty():
            try:
                segment = self._seg_q.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                results = engine.transcribe(segment)
                for result in results:
                    self._result_q.put(result)
            except Exception as exc:
                # Log and continue — one bad segment should not kill the worker
                logger.error("Erro ao transcrever segmento [%s]: %s", self.name, exc)
