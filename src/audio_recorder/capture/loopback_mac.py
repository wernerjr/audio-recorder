from __future__ import annotations

import queue
import time

import numpy as np
import sounddevice as sd

from .base import AudioCapturer, AudioChunk, AudioConfig

BLACKHOLE_NAME = "blackhole"


def _find_blackhole() -> dict | None:
    for i, d in enumerate(sd.query_devices()):
        if BLACKHOLE_NAME in d["name"].lower() and d["max_input_channels"] > 0:
            return {"index": i, **d}
    return None


class LoopbackCapturerMac(AudioCapturer):
    """
    Captures system audio on macOS via BlackHole virtual audio driver.
    Install BlackHole from: https://existential.audio/blackhole/
    """

    def __init__(
        self,
        config: AudioConfig,
        output_queue: queue.Queue[AudioChunk],
    ) -> None:
        super().__init__(config, output_queue, source="system")

    def _capture_loop(self) -> None:
        device = _find_blackhole()
        if device is None:
            raise RuntimeError(
                "BlackHole não encontrado. "
                "Instale em: https://existential.audio/blackhole/ "
                "e configure-o como dispositivo de saída de áudio."
            )

        sample_rate = self._config.sample_rate or int(device["default_samplerate"])
        channels = self._config.channels or min(int(device["max_input_channels"]), 2)

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
            device=device["index"],
            callback=callback,
        ):
            self._stop_event.wait()
