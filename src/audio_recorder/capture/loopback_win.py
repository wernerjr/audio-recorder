from __future__ import annotations

import queue
import time

from .base import AudioCapturer, AudioChunk, AudioConfig


class LoopbackCapturerWin(AudioCapturer):
    """Captures system audio (loopback) via WASAPI on Windows using pyaudiowpatch."""

    def __init__(
        self,
        config: AudioConfig,
        output_queue: queue.Queue[AudioChunk],
    ) -> None:
        super().__init__(config, output_queue, source="system")

    def _capture_loop(self) -> None:
        import pyaudiowpatch as pyaudio  # imported here — Windows only

        with pyaudio.PyAudio() as p:
            device_info = p.get_default_wasapi_loopback()
            sample_rate = int(device_info["defaultSampleRate"])
            channels = int(device_info["maxInputChannels"])

            self._actual_sample_rate = sample_rate
            self._actual_channels = channels

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=int(device_info["index"]),
                frames_per_buffer=self._config.chunk_size,
            )

            session_start = time.monotonic()
            try:
                while not self._stop_event.is_set():
                    data = stream.read(
                        self._config.chunk_size, exception_on_overflow=False
                    )
                    self._put(data, time.monotonic() - session_start)
            finally:
                stream.stop_stream()
                stream.close()


def list_loopback_devices_win() -> list[dict]:
    """Return WASAPI loopback devices available on Windows."""
    import pyaudiowpatch as pyaudio

    devices = []
    with pyaudio.PyAudio() as p:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("isLoopbackDevice"):
                devices.append({
                    "index": i,
                    "name": info["name"],
                    "channels": int(info["maxInputChannels"]),
                    "sample_rate": int(info["defaultSampleRate"]),
                })
    return devices
