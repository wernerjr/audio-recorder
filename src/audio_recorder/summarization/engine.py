from __future__ import annotations

import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

_SUMMARY_SENTENCES = 4   # sentences in the executive summary block
_BULLETS_PER_SPEAKER = 4  # max bullet points per speaker
_MIN_SENTENCE_WORDS = 6   # ignore very short fragments


def _ensure_nltk() -> None:
    import nltk
    for resource, kind in [("punkt_tab", "tokenizers"), ("stopwords", "corpora")]:
        try:
            nltk.data.find(f"{kind}/{resource}")
        except LookupError:
            logger.info("Baixando recurso NLTK: %s", resource)
            nltk.download(resource, quiet=True)


def _tokenize_sentences(text: str) -> list[str]:
    import nltk
    try:
        sents = nltk.sent_tokenize(text, language="portuguese")
    except Exception:
        sents = nltk.sent_tokenize(text, language="english")
    return [s.strip() for s in sents if len(s.split()) >= _MIN_SENTENCE_WORDS]


def _tfidf_scores(sentences: list[str]) -> dict[str, float]:
    """Return a TF-IDF importance score for each sentence."""
    import math
    from collections import Counter

    stop_words = _get_stopwords()

    def tokenize(s: str) -> list[str]:
        return [w.lower() for w in re.findall(r"\w+", s) if w.lower() not in stop_words]

    tokenized = [tokenize(s) for s in sentences]
    n = len(tokenized)
    if n == 0:
        return {}

    # IDF
    df: dict[str, int] = Counter()
    for tokens in tokenized:
        df.update(set(tokens))
    idf = {term: math.log((n + 1) / (freq + 1)) for term, freq in df.items()}

    # TF-IDF score per sentence = mean TF-IDF of its tokens
    scores: dict[str, float] = {}
    for sent, tokens in zip(sentences, tokenized):
        if not tokens:
            scores[sent] = 0.0
            continue
        tf: dict[str, float] = Counter(tokens)
        total = len(tokens)
        score = sum((tf[t] / total) * idf.get(t, 0) for t in tokens)
        scores[sent] = score / len(tokens)

    return scores


def _get_stopwords() -> set[str]:
    try:
        from nltk.corpus import stopwords
        words = set(stopwords.words("portuguese")) | set(stopwords.words("english"))
    except Exception:
        words = set()
    # always include common filler
    words |= {
        "né", "aí", "tá", "tô", "pra", "pro", "num", "numa",
        "então", "assim", "tipo", "cara", "né", "ok", "sim", "não",
    }
    return words


def _top_sentences(sentences: list[str], scores: dict[str, float], n: int) -> list[str]:
    ranked = sorted(sentences, key=lambda s: scores.get(s, 0), reverse=True)
    top = ranked[:n]
    # restore original order
    order = {s: i for i, s in enumerate(sentences)}
    return sorted(top, key=lambda s: order[s])


class SummarizationEngine:
    """
    Generates structured meeting minutes from transcript segments.

    Output format:
        RESUMO EXECUTIVO
        [key sentences as paragraph]

        PONTOS PRINCIPAIS
        • ...

        POR PARTICIPANTE (if speakers available)
        [SPEAKER_XX]
        • ...
    """

    DEFAULT_MODEL = "tfidf"  # kept for API compatibility

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self._model_id = model_id

    def summarize(self, segments: list[dict]) -> str:
        _ensure_nltk()

        if not segments:
            return "Nenhum segmento de transcrição disponível."

        # ── Build full text and per-speaker texts ────────────────────────
        all_sentences: list[str] = []
        speaker_sentences: dict[str, list[str]] = defaultdict(list)

        for seg in segments:
            speaker = seg.get("speaker") or seg.get("source", "desconhecido")
            sents = _tokenize_sentences(seg["text"])
            all_sentences.extend(sents)
            speaker_sentences[speaker].extend(sents)

        if not all_sentences:
            return "Transcrição muito curta para gerar ata."

        scores = _tfidf_scores(all_sentences)

        # ── Executive summary ────────────────────────────────────────────
        top = _top_sentences(all_sentences, scores, _SUMMARY_SENTENCES)
        summary_block = " ".join(top)

        lines: list[str] = [
            "RESUMO EXECUTIVO",
            "─" * 40,
            summary_block,
            "",
        ]

        # ── Overall bullet points ────────────────────────────────────────
        bullet_count = min(10, max(5, len(all_sentences) // 5))
        bullets = _top_sentences(all_sentences, scores, bullet_count)
        # remove sentences already in summary to avoid duplication
        summary_set = set(top)
        bullets = [b for b in bullets if b not in summary_set] or bullets

        lines += ["PONTOS PRINCIPAIS", "─" * 40]
        for b in bullets:
            lines.append(f"• {b}")
        lines.append("")

        # ── Per-speaker breakdown (only if diarization ran) ─────────────
        has_speakers = any(
            s.get("speaker") and s["speaker"].startswith("SPEAKER_")
            for s in segments
        )
        if has_speakers:
            lines += ["POR PARTICIPANTE", "─" * 40]
            for speaker, sents in sorted(speaker_sentences.items()):
                if not sents:
                    continue
                sp_scores = _tfidf_scores(sents)
                sp_bullets = _top_sentences(sents, sp_scores, _BULLETS_PER_SPEAKER)
                lines.append(f"[{speaker}]")
                for b in sp_bullets:
                    lines.append(f"  • {b}")
                lines.append("")

        return "\n".join(lines)
