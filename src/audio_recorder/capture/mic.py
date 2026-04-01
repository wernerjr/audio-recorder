from __future__ import annotations

import queue
import time

import numpy as np
import sounddevice as sd

from .base import AudioCapturer, AudioChunk, AudioConfig


class MicCapturer(AudioCapturer):
    """Captures microphone input using sounddevice (cross-platform)."""

    def __init__(
        self,
        config: AudioConfig,
        output_queue: queue.Queue[AudioChunk],
        device_index: int | None = None,
    ) -> None:
        super().__init__(config, output_queue, source="mic")
        self._device_index = device_index

    def _capture_loop(self) -> None:
        device_info = sd.query_devices(
            self._device_index if self._device_index is not None else sd.default.device[0]
        )
        sample_rate = self._config.sample_rate or int(device_info["default_samplerate"])
        channels = self._config.channels or min(int(device_info["max_input_channels"]), 2)
        channels = max(channels, 1)

        self._actual_sample_rate = sample_rate
        self._actual_channels = channels

        session_start = time.monotonic()

        def callback(
            indata: np.ndarray,
            frames: int,
            time_info: sd.CallbackFlags,
            status: sd.CallbackFlags,
        ) -> None:
            self._put(indata.tobytes(), time.monotonic() - session_start)

        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=self._config.chunk_size,
            device=self._device_index,
            callback=callback,
        ):
            self._stop_event.wait()


def list_mic_devices() -> list[dict]:
    """Return input devices available for microphone capture."""
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            devices.append({
                "index": i,
                "name": d["name"],
                "channels": d["max_input_channels"],
                "sample_rate": int(d["default_samplerate"]),
                "is_default": i == sd.default.device[0],
            })
    return devices
