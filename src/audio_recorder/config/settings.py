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

    if s.diarization.enabled and not s.diarization.token:
        logger.warning(
            "Diarização ativada mas token HuggingFace não configurado. "
            "Defina 'diarization.token' no config.toml ou HUGGINGFACE_TOKEN."
        )
