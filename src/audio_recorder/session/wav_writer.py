from __future__ import annotations

import logging
import queue
import threading
import wave
from pathlib import Path

from ..capture.base import AudioChunk

logger = logging.getLogger(__name__)


class WavWriter(threading.Thread):
    """
    Reads AudioChunks from a queue and writes them to a WAV file.
    The file is opened lazily on the first chunk (to get sample_rate/channels).
    Closes cleanly when stop_event is set and the queue is drained.
    """

    def __init__(
        self,
        path: Path,
        chunk_queue: queue.Queue[AudioChunk],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name=f"wav-writer-{path.stem}", daemon=True)
        self._path = path
        self._queue = chunk_queue
        self._stop_event = stop_event

    def run(self) -> None:
        wf: wave.Wave_write | None = None
        try:
            while not self._stop_event.is_set() or not self._queue.empty():
                try:
                    chunk = self._queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                if wf is None:
                    wf = wave.open(str(self._path), "wb")
                    wf.setnchannels(chunk.channels or 1)
                    wf.setsampwidth(2)  # Int16
                    wf.setframerate(chunk.sample_rate or 44100)
                    logger.debug("WAV aberto: %s (%dHz, %dch)", self._path.name,
                                 chunk.sample_rate, chunk.channels)

                wf.writeframes(chunk.data)

        except Exception:
            logger.exception("Erro no WavWriter '%s'", self._path.name)
        finally:
            if wf is not None:
                wf.close()
                logger.debug("WAV fechado: %s", self._path.name)
