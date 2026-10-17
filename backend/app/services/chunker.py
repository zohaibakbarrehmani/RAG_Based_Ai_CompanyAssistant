from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

TARGET_WORDS = 375
OVERLAP_WORDS = 45


@dataclass(frozen=True)
class TextChunk:
    page: int
    section: str
    text: str
    token_estimate: int
    chunk_hash: str


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.split()) * 4 + 2) // 3)


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = part.split()
        if len(words) <= TARGET_WORDS:
            if words:
                sentences.append(" ".join(words))
            continue

        start = 0
        while start < len(words):
            end = min(start + TARGET_WORDS, len(words))
            sentences.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start = end
    return sentences


def _split_unit(page: int, section: str, text: str) -> list[TextChunk]:
    sentences = _sentences(text)
    chunks: list[TextChunk] = []
    current_words: list[str] = []

    def save_chunk() -> None:
        if not current_words:
            return
        chunk_text = " ".join(current_words)
        chunks.append(
            TextChunk(
                page=page,
                section=section,
                text=chunk_text,
                token_estimate=_estimate_tokens(chunk_text),
                chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
            )
        )

    for sentence in sentences:
        sentence_words = sentence.split()
        if current_words and len(current_words) + len(sentence_words) > TARGET_WORDS:
            save_chunk()
            current_words = current_words[-OVERLAP_WORDS:]
        current_words.extend(sentence_words)

    save_chunk()
    return chunks


def chunk_parsed_sections(sections: list[dict[str, Any]]) -> list[TextChunk]:
    """Chunk each parsed page/section independently to preserve citation metadata."""
    chunks: list[TextChunk] = []
    for section in sections:
        text = str(section.get("text", "")).strip()
        if not text:
            continue
        chunks.extend(
            _split_unit(
                page=int(section.get("page", 1)),
                section=str(section.get("section") or "General"),
                text=text,
            )
        )
    return chunks
