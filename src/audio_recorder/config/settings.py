from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_MODELS = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}


@dataclass
class CaptureSettings:
    mic_device_name: str = ""
    chunk_size: int = 1024


@dataclass
class TranscriptionSettings:
    model: str = "small"
    language: str = "auto"
    vad_silence_ms: int = 500
    vad_overlap_ms: int = 200


@dataclass
class OutputSettings:
    directory: str = "recordings"
    db_path: str = ""  # caminho do history.db; vazio → <output_dir>/history.db


@dataclass
class DiarizationSettings:
    enabled: bool = False
    token: str = ""


@dataclass
class Settings:
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    transcription: TranscriptionSettings = field(default_factory=TranscriptionSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    diarization: DiarizationSettings = field(default_factory=DiarizationSettings)


def _merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(path: Path | None = None) -> Settings:
    defaults_path = Path(__file__).parent / "defaults.toml"
    with open(defaults_path, "rb") as f:
        data = tomllib.load(f)

    if path and path.exists():
        with open(path, "rb") as f:
            user_data = tomllib.load(f)
        data = _merge(data, user_data)

    # env var overrides
    hf_token = os.environ.get("HUGGINGFACE_TOKEN", "")
    if hf_token:
        data.setdefault("diarization", {})["token"] = hf_token

    capture = CaptureSettings(**data.get("capture", {}))
    transcription = TranscriptionSettings(**data.get("transcription", {}))
    output_data = {k: v for k, v in data.get("output", {}).items() if k in ("directory", "db_path")}
    output = OutputSettings(**output_data)
    diarization = DiarizationSettings(**data.get("diarization", {}))

    settings = Settings(
        capture=capture,
        transcription=transcription,
        output=output,
        diarization=diarization,
    )
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    if s.transcription.model not in VALID_MODELS:
        raise ValueError(
            f"Modelo inválido: '{s.transcription.model}'. "
            f"Válidos: {sorted(VALID_MODELS)}"
        )

    if s.diarization.enabled:
        logger.debug("Diarização ativada com modelo público freevoid/speaker-diarization-3.1.")


def settings_to_dict(s: Settings) -> dict[str, str]:
    """Serialize Settings to a flat key/value dict for SQLite storage."""
    return {
        "capture.mic_device_name": s.capture.mic_device_name,
        "capture.chunk_size": str(s.capture.chunk_size),
        "transcription.model": s.transcription.model,
        "transcription.language": s.transcription.language,
        "transcription.vad_silence_ms": str(s.transcription.vad_silence_ms),
        "transcription.vad_overlap_ms": str(s.transcription.vad_overlap_ms),
        "output.directory": s.output.directory,
        "output.db_path": s.output.db_path,
        "diarization.enabled": "1" if s.diarization.enabled else "0",
        "diarization.token": s.diarization.token,
    }


def settings_from_dict(d: dict[str, str], base: Settings | None = None) -> Settings:
    """Deserialize a flat key/value dict (from SQLite) back into a Settings object."""
    s = base or Settings()
    if "capture.mic_device_name" in d:
        s.capture.mic_device_name = d["capture.mic_device_name"]
    if "capture.chunk_size" in d:
        s.capture.chunk_size = int(d["capture.chunk_size"])
    if "transcription.model" in d:
        s.transcription.model = d["transcription.model"]
    if "transcription.language" in d:
        s.transcription.language = d["transcription.language"]
    if "transcription.vad_silence_ms" in d:
        s.transcription.vad_silence_ms = int(d["transcription.vad_silence_ms"])
    if "transcription.vad_overlap_ms" in d:
        s.transcription.vad_overlap_ms = int(d["transcription.vad_overlap_ms"])
    if "output.directory" in d:
        s.output.directory = d["output.directory"]
    if "output.db_path" in d:
        s.output.db_path = d["output.db_path"]
    if "diarization.enabled" in d:
        s.diarization.enabled = d["diarization.enabled"] == "1"
    if "diarization.token" in d:
        s.diarization.token = d["diarization.token"]
    return s
