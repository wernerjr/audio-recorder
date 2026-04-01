from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AudioChunk:
    data: bytes          # PCM Int16, interleaved
    timestamp: float     # monotonic seconds from session start
    source: str          # "mic" | "system"


@dataclass
class AudioConfig:
    chunk_size: int = 1024
    sample_rate: int | None = None   # None = auto-detect from device
    channels: int | None = None      # None = auto-detect from device


class AudioCapturer(ABC):
    """Base class for all audio capture implementations."""

    def __init__(
        self,
        config: AudioConfig,
        output_queue: queue.Queue[AudioChunk],
        source: str,
    ) -> None:
        self._config = config
        self._queue = output_queue
        self._source = source
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._actual_sample_rate: int = 0
        self._actual_channels: int = 0

    @abstractmethod
    def _capture_loop(self) -> None: ...

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"capture-{self._source}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def sample_rate(self) -> int:
        return self._actual_sample_rate or (self._config.sample_rate or 44100)

    @property
    def channels(self) -> int:
        return self._actual_channels or (self._config.channels or 1)

    def _put(self, data: bytes, timestamp: float) -> None:
        chunk = AudioChunk(data=data, timestamp=timestamp, source=self._source)
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            pass  # drop chunk under backpressure
