from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

from ..capture.base import AudioCapturer, AudioChunk, AudioConfig
from ..capture.factory import get_loopback_capturer, get_mic_capturer
from ..config.settings import Settings
from ..merge.merger import Merger, MergedSegment
from ..audio.mixer import mix_wav
from ..persistence.database import get_db, save_session
from ..transcription.segment import TranscriptResult
from .state import SessionState
from .wav_writer import WavWriter

logger = logging.getLogger(__name__)

_QUEUE_WAV_SIZE = 200
_SOURCE_FILES = ["microfone.wav", "sistema.wav", "microfone.offset", "sistema.offset"]


def _cleanup_source_files(output_dir: Path) -> None:
    """Remove individual channel files after a successful merge."""
    for name in _SOURCE_FILES:
        p = output_dir / name
        try:
            if p.exists():
                p.unlink()
        except OSError:
            logger.warning("Não foi possível remover %s", p)


class RecordingSession:
    """
    Manages the full lifecycle of one recording session:
      start() → RECORDING (capturers + wav writers running)
      stop()  → DONE (wav files written to disk)
      transcribe_recordings() → run Whisper on the saved wav files
      merge_and_save() → merge + SQLite persistence

    Thread layout per channel (mic and system):
      Capturer → wav_q → WavWriter → <channel>.wav
    """

    def __init__(self, settings: Settings, output_dir: Path) -> None:
        self._settings = settings
        self._output_dir = output_dir
        self.state = SessionState.IDLE
        self._stop_event = threading.Event()
        self._capturers: list[AudioCapturer] = []
        self._workers: list[threading.Thread] = []
        self._started_at: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self.state != SessionState.IDLE:
            raise RuntimeError(f"Sessão já iniciada (estado: {self.state})")

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now().isoformat()
        cfg = AudioConfig(chunk_size=1024)

        for source, wav_name, kwargs in [
            ("mic",    "microfone.wav", {"device_name": self._settings.capture.mic_device_name}),
            ("system", "sistema.wav",   {}),
        ]:
            capturer, workers = self._build_channel(
                source, cfg,
                self._output_dir / wav_name, **kwargs,
            )
            self._capturers.append(capturer)
            self._workers.extend(workers)

        for w in self._workers:
            w.start()
        for c in self._capturers:
            c.start()

        self.state = SessionState.RECORDING
        logger.info("Gravação iniciada → %s", self._output_dir)

    def stop(self) -> None:
        if self.state != SessionState.RECORDING:
            return

        logger.info("Parando gravação, aguardando wav writers...")

        for c in self._capturers:
            c.stop()

        self._stop_event.set()

        for w in self._workers:
            w.join(timeout=30)
            if w.is_alive():
                logger.warning("Worker '%s' não terminou no prazo.", w.name)

        self.state = SessionState.DONE
        logger.info("Gravação concluída, arquivos WAV prontos.")

    def transcribe_recordings(self) -> list[TranscriptResult]:
        """Transcribe the recorded WAV files using Whisper. Call after stop()."""
        from ..transcription.engine import WhisperEngine

        t = self._settings.transcription
        engine = WhisperEngine(t.model, t.language)

        results: list[TranscriptResult] = []
        for source, wav_name in [("mic", "microfone.wav"), ("system", "sistema.wav")]:
            wav_path = self._output_dir / wav_name
            if wav_path.exists():
                logger.info("Transcrevendo %s (%s)…", wav_name, source)
                results.extend(engine.transcribe_file(wav_path, source))

        results.sort(key=lambda r: r.start)
        return results

    def merge_and_save(
        self,
        results: list[TranscriptResult],
        diarization_segments: list | None = None,
    ) -> None:
        """Merge transcription results and persist to SQLite history."""
        mic_results = [r for r in results if r.source == "mic"]
        sys_results = [r for r in results if r.source == "system"]

        segments: list[MergedSegment] = Merger().merge(
            mic_results, sys_results, diarization_segments
        )

        merged_wav_str: str | None = None
        try:
            merged_path = self._output_dir / "merged.wav"
            mix_wav(
                self._output_dir / "microfone.wav",
                self._output_dir / "sistema.wav",
                merged_path,
            )
            merged_wav_str = str(merged_path)
            _cleanup_source_files(self._output_dir)
        except Exception:
            logger.exception("Falha ao mixar áudio.")

        db_path = (
            Path(self._settings.output.db_path)
            if self._settings.output.db_path
            else Path(self._settings.output.directory) / "history.db"
        )
        try:
            db = get_db(db_path)
            save_session(
                db, self._output_dir, self._started_at, datetime.now().isoformat(),
                segments, merged_wav=merged_wav_str,
            )
            db.close()
            logger.info("Sessão salva no histórico: %s", db_path)
        except Exception:
            logger.exception("Falha ao salvar sessão no histórico SQLite.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_channel(
        self,
        source: str,
        cfg: AudioConfig,
        wav_path: Path,
        device_name: str = "",
    ) -> tuple[AudioCapturer, list[threading.Thread]]:
        """Return (capturer, [worker_threads]) for one audio channel."""
        wav_q: queue.Queue[AudioChunk] = queue.Queue(maxsize=_QUEUE_WAV_SIZE)

        if source == "mic":
            capturer = get_mic_capturer([wav_q], cfg, device_name=device_name)
        else:
            capturer = get_loopback_capturer([wav_q], cfg)

        workers: list[threading.Thread] = [
            WavWriter(wav_path, wav_q, self._stop_event),
        ]
        return capturer, workers


def session_output_dir(base_dir: str | Path) -> Path:
    """Return a timestamped output directory path (not yet created)."""
    name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(base_dir) / name
