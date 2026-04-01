from __future__ import annotations

import queue

from .base import AudioCapturer, AudioConfig, AudioChunk
from .mic import MicCapturer, list_mic_devices
from ..utils.platform import Platform, current_platform


def get_loopback_capturer(
    output_queues: queue.Queue[AudioChunk] | list[queue.Queue[AudioChunk]],
    config: AudioConfig | None = None,
) -> AudioCapturer:
    """Instantiate the correct loopback capturer for the current platform."""
    if config is None:
        config = AudioConfig()

    platform = current_platform()

    if platform == Platform.WINDOWS:
        from .loopback_win import LoopbackCapturerWin
        return LoopbackCapturerWin(config, output_queues)

    if platform == Platform.MACOS:
        from .loopback_mac import LoopbackCapturerMac
        return LoopbackCapturerMac(config, output_queues)

    if platform == Platform.LINUX:
        from .loopback_linux import LoopbackCapturerLinux
        return LoopbackCapturerLinux(config, output_queues)

    raise NotImplementedError(f"Loopback não suportado nesta plataforma: {platform}")


def get_mic_capturer(
    output_queues: queue.Queue[AudioChunk] | list[queue.Queue[AudioChunk]],
    config: AudioConfig | None = None,
    device_name: str = "",
    device_index: int | None = None,
) -> MicCapturer:
    """Instantiate a MicCapturer, optionally finding a device by name substring."""
    if config is None:
        config = AudioConfig()

    if device_name and device_index is None:
        device_index = _find_device_by_name(device_name)

    return MicCapturer(config, output_queues, device_index=device_index)


def list_devices() -> dict[str, list[dict]]:
    """Return available audio devices grouped by type."""
    mics = list_mic_devices()
    loopback = _list_loopback_devices()
    return {"mics": mics, "loopback": loopback}


def _find_device_by_name(name: str) -> int | None:
    needle = name.lower()
    for d in list_mic_devices():
        if needle in d["name"].lower():
            return d["index"]
    return None


def _list_loopback_devices() -> list[dict]:
    platform = current_platform()
    try:
        if platform == Platform.WINDOWS:
            from .loopback_win import list_loopback_devices_win
            return list_loopback_devices_win()

        # macOS / Linux: show monitor/blackhole devices from sounddevice
        import sounddevice as sd
        keyword = "blackhole" if platform == Platform.MACOS else "monitor"
        result = []
        for i, d in enumerate(sd.query_devices()):
            if keyword in d["name"].lower() and d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name": d["name"],
                    "channels": int(d["max_input_channels"]),
                    "sample_rate": int(d["default_samplerate"]),
                })
        return result
    except Exception:
        return []
