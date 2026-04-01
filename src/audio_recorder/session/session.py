from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

from ..capture.base import AudioCapturer, AudioChunk, AudioConfig
from ..capture.factory import get_loopback_capturer, get_mic_capturer
from ..config.settings import Settings
from ..merge.formatter import write_all
from ..merge.merger import Merger, MergedSegment
from ..persistence.database import get_db, save_session
from ..transcription.segment import AudioSegment, TranscriptResult
from ..vad.silero import VADWorker
from ..transcription.pipeline import TranscriptionWorker
from .state import SessionState
from .wav_writer import WavWriter

logger = logging.getLogger(__name__)

_QUEUE_RAW_SIZE = 200
_QUEUE_WAV_SIZE = 200
_QUEUE_SEG_SIZE = 50


class RecordingSession:
    """
    Manages the full lifecycle of one recording session:
      start() → RECORDING (all workers running)
      stop()  → TRANSCRIBING (workers drain) → DONE
      merge_and_save() → output files on disk

    Thread layout per channel (mic and system):
      Capturer → [raw_q, wav_q]
                    |         └─ WavWriter → <channel>.wav
                    └─ VADWorker → segment_q → TranscriptionWorker → result_queue
    """

    def __init__(self, settings: Settings, output_dir: Path) -> None:
        self._settings = settings
        self._output_dir = output_dir
        self.state = SessionState.IDLE
        self.result_queue: queue.Queue[TranscriptResult] = queue.Queue()
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
        t = self._settings.transcription

        for source, wav_name, kwargs in [
            ("mic",    "microfone.wav", {"device_name": self._settings.capture.mic_device_name}),
            ("system", "sistema.wav",   {}),
        ]:
            capturer, workers = self._build_channel(
                source, cfg, t.model, t.language,
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

        self.state = SessionState.TRANSCRIBING
        logger.info("Parando gravação, aguardando workers...")

        # 1. Stop capturers first — cuts off data flow into the queues
        for c in self._capturers:
            c.stop()

        # 2. Signal the remaining workers (WavWriter, VADWorker, TranscriptionWorker)
        self._stop_event.set()

        # 3. Wait for workers to drain their queues
        for w in self._workers:
            w.join(timeout=60)
            if w.is_alive():
                logger.warning("Worker '%s' não terminou no prazo.", w.name)

        self.state = SessionState.DONE
        logger.info("Sessão concluída.")

    def merge_and_save(
        self,
        results: list[TranscriptResult],
        diarization_segments: list | None = None,
    ) -> list[Path]:
        """Run merger + formatter and write output files. Returns created paths."""
        mic_results = [r for r in results if r.source == "mic"]
        sys_results = [r for r in results if r.source == "system"]

        segments: list[MergedSegment] = Merger().merge(
            mic_results, sys_results, diarization_segments
        )

        base = self._output_dir / "merged_transcript"
        created = write_all(segments, base, self._settings.output.formats)

        for path in created:
            logger.info("Arquivo gerado: %s", path)

        # Persist to SQLite history
        db_path = (
            Path(self._settings.output.db_path)
            if self._settings.output.db_path
            else Path(self._settings.output.directory) / "history.db"
        )
        try:
            db = get_db(db_path)
            save_session(db, self._output_dir, self._started_at, datetime.now().isoformat(), segments)
            db.close()
            logger.info("Sessão salva no histórico: %s", db_path)
        except Exception:
            logger.exception("Falha ao salvar sessão no histórico SQLite.")

        return created

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_channel(
        self,
        source: str,
        cfg: AudioConfig,
        model: str,
        language: str,
        wav_path: Path,
        device_name: str = "",
    ) -> tuple[AudioCapturer, list[threading.Thread]]:
        """Return (capturer, [worker_threads]) for one audio channel."""
        raw_q: queue.Queue[AudioChunk] = queue.Queue(maxsize=_QUEUE_RAW_SIZE)
        wav_q: queue.Queue[AudioChunk] = queue.Queue(maxsize=_QUEUE_WAV_SIZE)
        seg_q: queue.Queue[AudioSegment] = queue.Queue(maxsize=_QUEUE_SEG_SIZE)

        t = self._settings.transcription

        if source == "mic":
            capturer = get_mic_capturer([raw_q, wav_q], cfg, device_name=device_name)
        else:
            capturer = get_loopback_capturer([raw_q, wav_q], cfg)

        workers: list[threading.Thread] = [
            WavWriter(wav_path, wav_q, self._stop_event),
            VADWorker(
                raw_q, seg_q, self._stop_event,
                source=source,
                silence_ms=t.vad_silence_ms,
                speech_pad_ms=t.vad_overlap_ms,
            ),
            TranscriptionWorker(
                seg_q, self.result_queue, self._stop_event,
                model_name=model, language=language, source=source,
            ),
        ]
        return capturer, workers


def session_output_dir(base_dir: str | Path) -> Path:
    """Return a timestamped output directory path (not yet created)."""
    name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(base_dir) / name
