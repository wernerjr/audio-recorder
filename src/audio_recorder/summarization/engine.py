from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MAX_INPUT_TOKENS = 1024   # BART-large-cnn hard limit
_MAX_OUTPUT_TOKENS = 512


class SummarizationEngine:
    """
    Generates meeting minutes from a list of transcript segments using a
    HuggingFace summarization model (default: facebook/bart-large-cnn).

    The pipeline is loaded lazily on the first call to summarize().
    """

    DEFAULT_MODEL = "facebook/bart-large-cnn"

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self._model_id = model_id
        self._pipeline = None  # lazy load

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        from transformers import pipeline
        logger.info("Carregando modelo de sumarização: %s", self._model_id)
        self._pipeline = pipeline(
            "summarization",
            model=self._model_id,
            tokenizer=self._model_id,
        )
        logger.info("Modelo carregado.")

    def summarize(self, segments: list[dict]) -> str:
        """
        Build a meeting minutes text from *segments*.

        Each segment dict must have at least: text, start, end, source.
        Optional: speaker.

        Returns the generated summary string.
        """
        self._load()
        assert self._pipeline is not None

        # Build readable transcript text for the model
        lines: list[str] = []
        for seg in segments:
            speaker = seg.get("speaker") or seg.get("source", "")
            lines.append(f"[{speaker}] {seg['text']}")
        full_text = " ".join(lines)

        logger.debug("Texto de entrada para sumarização: %d chars", len(full_text))

        result = self._pipeline(
            full_text,
            max_length=_MAX_OUTPUT_TOKENS,
            min_length=64,
            truncation=True,
            do_sample=False,
        )
        return result[0]["summary_text"]
