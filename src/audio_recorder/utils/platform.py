from __future__ import annotations

import sys
from enum import Enum


class Platform(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


def current_platform() -> Platform:
    if sys.platform == "win32":
        return Platform.WINDOWS
    if sys.platform == "darwin":
        return Platform.MACOS
    if sys.platform.startswith("linux"):
        return Platform.LINUX
    return Platform.UNKNOWN


def check_loopback_dependency() -> tuple[bool, str]:
    """
    Check if the loopback capture dependency is available for the current platform.
    Returns (ok, message).
    """
    platform = current_platform()

    if platform == Platform.WINDOWS:
        try:
            import pyaudiowpatch  # noqa: F401
            return True, "pyaudiowpatch disponível (WASAPI loopback)."
        except ImportError:
            return False, (
                "pyaudiowpatch não encontrado. Instale com: uv sync"
            )

    if platform == Platform.MACOS:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_blackhole = any(
                "blackhole" in str(d["name"]).lower() for d in devices
            )
            if has_blackhole:
                return True, "BlackHole encontrado para loopback no macOS."
            return False, (
                "BlackHole não encontrado. Instale em: https://existential.audio/blackhole/"
            )
        except Exception:
            return False, "sounddevice não disponível."

    if platform == Platform.LINUX:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_monitor = any(
                "monitor" in str(d["name"]).lower() for d in devices
            )
            if has_monitor:
                return True, "Monitor source encontrado (PulseAudio/PipeWire)."
            return False, (
                "Nenhum monitor source encontrado. Verifique se PulseAudio ou PipeWire está ativo."
            )
        except Exception:
            return False, "sounddevice não disponível."

    return False, f"Plataforma não suportada: {sys.platform}"
