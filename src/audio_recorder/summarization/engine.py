from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_SENTENCES = 15


class SummarizationEngine:
    """
    Generates meeting minutes from a list of transcript segments using
    extractive summarization (sumy LSA) — no PyTorch or model download required.
    """

    DEFAULT_MODEL = "lsa"  # kept for API compatibility; value is ignored

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self._model_id = model_id

    def summarize(self, segments: list[dict]) -> str:
        """
        Build a meeting minutes text from *segments*.

        Each segment dict must have at least: text, start, end, source.
        Optional: speaker.

        Returns the generated summary string.
        """
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.summarizers.lsa import LsaSummarizer

        # Build readable transcript
        lines: list[str] = []
        for seg in segments:
            speaker = seg.get("speaker") or seg.get("source", "")
            lines.append(f"[{speaker}] {seg['text']}")
        full_text = " ".join(lines)

        logger.debug("Texto de entrada para sumarização: %d chars", len(full_text))

        # Try Portuguese tokenizer, fall back to English
        for lang in ("portuguese", "english"):
            try:
                tokenizer = Tokenizer(lang)
                break
            except Exception:
                continue
        else:
            tokenizer = Tokenizer("english")

        parser = PlaintextParser.from_string(full_text, tokenizer)
        summarizer = LsaSummarizer()

        # Scale sentence count to transcript length
        doc_sentences = len(list(parser.document.sentences))
        count = min(_DEFAULT_SENTENCES, max(3, doc_sentences // 3))

        sentences = summarizer(parser.document, count)
        return "\n\n".join(str(s) for s in sentences)
