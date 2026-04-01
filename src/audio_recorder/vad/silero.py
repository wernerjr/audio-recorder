from __future__ import annotations

import queue
import threading
from math import gcd

import numpy as np

from ..capture.base import AudioChunk
from ..transcription.segment import AudioSegment

VAD_SAMPLE_RATE = 16000
FRAME_SIZE = 512          # samples at 16kHz = 32ms per frame
MAX_SEGMENT_SECONDS = 30  # safety valve: force-emit after this duration


def _to_mono_float32(data: bytes, channels: int) -> np.ndarray:
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio
    import scipy.signal
    g = gcd(dst_rate, src_rate)
    return scipy.signal.resample_poly(audio, dst_rate // g, src_rate // g).astype(np.float32)


class VADWorker(threading.Thread):
    """
    Reads AudioChunks from raw_queue, uses Silero VAD to detect speech
    boundaries, and emits AudioSegments into segment_queue.

    Each emitted AudioSegment contains the PCM bytes of a single speech
    utterance at the original sample rate and channel count.
    """

    def __init__(
        self,
        raw_queue: queue.Queue[AudioChunk],
        segment_queue: queue.Queue[AudioSegment],
        stop_event: threading.Event,
        source: str,
        silence_ms: int = 500,
        speech_pad_ms: int = 200,
    ) -> None:
        super().__init__(name=f"vad-{source}", daemon=True)
        self._raw_q = raw_queue
        self._seg_q = segment_queue
        self._stop_event = stop_event
        self._source = source
        self._silence_ms = silence_ms
        self._speech_pad_ms = speech_pad_ms

    def run(self) -> None:
        import torch
        from silero_vad import VADIterator, load_silero_vad

        model = load_silero_vad()
        vad_iter = VADIterator(
            model,
            threshold=0.5,
            sampling_rate=VAD_SAMPLE_RATE,
            min_silence_duration_ms=self._silence_ms,
            speech_pad_ms=self._speech_pad_ms,
        )

        vad_buffer = np.empty(0, dtype=np.float32)  # pending 16kHz samples
        speech_chunks: list[AudioChunk] = []
        speech_start: float | None = None  # session-relative seconds

        while not self._stop_event.is_set() or not self._raw_q.empty():
            try:
                chunk = self._raw_q.get(timeout=0.05)
            except queue.Empty:
                continue

            # Accumulate original-rate chunks during speech
            if speech_start is not None:
                speech_chunks.append(chunk)

            # Convert to 16kHz mono float32 for VAD
            mono = _to_mono_float32(chunk.data, chunk.channels or 1)
            resampled = _resample(mono, chunk.sample_rate or VAD_SAMPLE_RATE, VAD_SAMPLE_RATE)
            vad_buffer = np.concatenate([vad_buffer, resampled])

            # Process in fixed-size frames
            while len(vad_buffer) >= FRAME_SIZE:
                frame = torch.from_numpy(vad_buffer[:FRAME_SIZE])
                vad_buffer = vad_buffer[FRAME_SIZE:]

                event: dict = vad_iter(frame, return_seconds=True) or {}

                if "start" in event and speech_start is None:
                    speech_start = chunk.timestamp
                    speech_chunks = [chunk]

                if "end" in event and speech_start is not None:
                    self._emit(speech_chunks, speech_start, chunk.timestamp)
                    speech_start = None
                    speech_chunks = []

            # Safety valve: flush if segment exceeds max duration
            if (
                speech_start is not None
                and speech_chunks
                and chunk.timestamp - speech_start >= MAX_SEGMENT_SECONDS
            ):
                self._emit(speech_chunks, speech_start, chunk.timestamp)
                speech_start = chunk.timestamp
                speech_chunks = []

        # Flush any remaining speech when recording stops
        if speech_start is not None and speech_chunks:
            last_ts = speech_chunks[-1].timestamp
            self._emit(speech_chunks, speech_start, last_ts)

    def _emit(
        self,
        chunks: list[AudioChunk],
        start: float,
        end: float,
    ) -> None:
        if not chunks:
            return
        data = b"".join(c.data for c in chunks)
        segment = AudioSegment(
            data=data,
            sample_rate=chunks[0].sample_rate or VAD_SAMPLE_RATE,
            channels=chunks[0].channels or 1,
            start=start,
            end=end,
            source=self._source,
        )
        self._seg_q.put(segment)
