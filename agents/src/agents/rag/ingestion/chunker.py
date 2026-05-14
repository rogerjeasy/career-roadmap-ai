"""Text chunkers for the RAG ingestion pipeline.

Two strategies are available:

``Chunker``
    Paragraph-first sliding window (character-level). Kept for backward
    compatibility and lower-latency use-cases where semantic precision is
    less critical.

``SemanticChunker``
    Sentence-aware grouping with sentence-level overlap and rich metadata.
    This is the default for production ingestion.

    Strategy:
      1. Split on paragraph boundaries (\\n\\n) — primary structural unit.
      2. Within each paragraph, split on sentence endings (.  !  ?).
      3. Greedily group sentences into windows of ~target_chars characters.
      4. Carry over the last ``overlap_sentences`` sentences from the
         previous window so context is preserved across chunk boundaries.
      5. ``role``, ``industry``, and ``country`` from doc.metadata are
         promoted as first-class indexed fields for filtered retrieval.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from agents.rag.models import Chunk, Document
from agents.rag.observability import RAG_CHUNKER_CHUNKS_PER_DOC, RAG_CHUNKER_DURATION

# ── Shared constants ───────────────────────────────────────────────────────────

_TARGET_CHARS = 2000
_OVERLAP_CHARS = 200

# SemanticChunker defaults: ~400 tokens × 4 chars/token
_SEMANTIC_TARGET_CHARS = 1600
_SEMANTIC_OVERLAP_SENTENCES = 2

# Sentence boundary: ends with .!? followed by whitespace and an uppercase letter/quote
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'])')


# ── SemanticChunker ────────────────────────────────────────────────────────────


class SemanticChunker:
    """Splits Documents into semantically coherent Chunks.

    Chunk boundaries follow sentence edges, not arbitrary character windows.
    Overlap is measured in sentences rather than characters, so each chunk
    always starts on a complete thought.
    """

    def __init__(
        self,
        *,
        target_chars: int = _SEMANTIC_TARGET_CHARS,
        overlap_sentences: int = _SEMANTIC_OVERLAP_SENTENCES,
    ) -> None:
        self._target = target_chars
        self._overlap = overlap_sentences

    def chunk(self, doc: Document) -> list[Chunk]:
        """Return semantically chunked Chunk objects for one Document."""
        t0 = time.monotonic()
        sentences = _to_sentences(doc.content)
        windows = _sentences_to_windows(sentences, self._target, self._overlap)
        base_meta = _build_semantic_meta(doc)

        chunks: list[Chunk] = []
        for window in windows:
            text = " ".join(window)
            chunk_id = f"{doc.doc_id}::{uuid.uuid4().hex[:12]}"
            start = max(doc.content.find(window[0][:50]), 0)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type,
                    content=text,
                    char_start=start,
                    char_end=start + len(text),
                    metadata=base_meta,
                )
            )

        result = chunks or [_semantic_fallback(doc, base_meta)]
        RAG_CHUNKER_DURATION.labels(doc_type=doc.doc_type.value).observe(time.monotonic() - t0)
        RAG_CHUNKER_CHUNKS_PER_DOC.observe(len(result))
        return result


# ── Chunker (original sliding-window) ─────────────────────────────────────────


class Chunker:
    """Splits Documents into overlapping text Chunks. Stateless."""

    def __init__(
        self,
        *,
        target_chars: int = _TARGET_CHARS,
        overlap_chars: int = _OVERLAP_CHARS,
    ) -> None:
        self._target = target_chars
        self._overlap = overlap_chars

    def chunk(self, doc: Document) -> list[Chunk]:
        """Return overlapping Chunk objects for one Document."""
        paragraphs = _split_paragraphs(doc.content, self._target)
        windows = _merge_into_windows(paragraphs, self._target, self._overlap)

        base_meta: dict[str, Any] = {
            "title": doc.title,
            "source_url": doc.source_url or "",
            "language": doc.language,
            **{k: v for k, v in doc.metadata.items() if isinstance(v, (str, int, float, bool))},
        }

        chunks: list[Chunk] = []
        for window in windows:
            chunk_id = f"{doc.doc_id}::{uuid.uuid4().hex[:12]}"
            start = doc.content.find(window[:60])
            start = max(start, 0)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type,
                    content=window,
                    char_start=start,
                    char_end=start + len(window),
                    metadata=base_meta,
                )
            )

        return chunks or [_fallback_chunk(doc, base_meta)]


# ── SemanticChunker helpers ────────────────────────────────────────────────────


def _to_sentences(text: str) -> list[str]:
    """Break text into individual sentences via paragraph → sentence hierarchy."""
    result: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        parts = _SENTENCE_SPLIT.split(para)
        for part in parts:
            s = part.strip()
            if len(s) > 15:
                result.append(s)
    return result


def _sentences_to_windows(
    sentences: list[str], target: int, overlap: int
) -> list[list[str]]:
    """Group sentences into windows, carrying over the last ``overlap`` sentences."""
    if not sentences:
        return []

    windows: list[list[str]] = []
    current: list[str] = []
    current_chars = 0

    for sent in sentences:
        sent_chars = len(sent) + 1  # +1 for joining space
        if current_chars + sent_chars > target and current:
            windows.append(list(current))
            tail = current[-overlap:] if overlap else []
            current = list(tail)
            current_chars = sum(len(s) + 1 for s in current)
        current.append(sent)
        current_chars += sent_chars

    if current:
        windows.append(current)
    return windows


def _build_semantic_meta(doc: Document) -> dict[str, Any]:
    """Build chunk metadata, promoting role/industry/country as first-class fields."""
    meta: dict[str, Any] = {
        "title": doc.title,
        "source_url": doc.source_url or "",
        "language": doc.language,
    }
    # First-class filtering dimensions for Pinecone metadata filters
    for key in ("role", "industry", "country"):
        val = doc.metadata.get(key)
        if val and isinstance(val, str):
            meta[key] = val
    # Pass through remaining scalar metadata
    for k, v in doc.metadata.items():
        if k not in meta and isinstance(v, (str, int, float, bool)):
            meta[k] = v
    return meta


def _semantic_fallback(doc: Document, meta: dict[str, Any]) -> Chunk:
    cap = _SEMANTIC_TARGET_CHARS * 4
    return Chunk(
        chunk_id=f"{doc.doc_id}::full",
        doc_id=doc.doc_id,
        doc_type=doc.doc_type,
        content=doc.content[:cap],
        char_start=0,
        char_end=min(len(doc.content), cap),
        metadata=meta,
    )


# ── Chunker helpers ────────────────────────────────────────────────────────────


def _split_paragraphs(text: str, target: int) -> list[str]:
    """Split on blank lines; break long paragraphs on sentence boundaries."""
    raw = [p.strip() for p in text.split("\n\n") if p.strip()]
    result: list[str] = []
    for para in raw:
        if len(para) <= target:
            result.append(para)
        else:
            result.extend(_split_sentences(para))
    return result


def _split_sentences(text: str) -> list[str]:
    """Split on ``'. '`` boundaries."""
    parts = text.split(". ")
    sentences: list[str] = []
    for i, part in enumerate(parts):
        sentence = (part + ". ") if i < len(parts) - 1 else part
        if sentence.strip():
            sentences.append(sentence.strip())
    return sentences or [text]


def _merge_into_windows(paragraphs: list[str], target: int, overlap: int) -> list[str]:
    """Greedily merge paragraphs into windows with trailing overlap."""
    if not paragraphs:
        return []

    windows: list[str] = []
    current = paragraphs[0]

    for para in paragraphs[1:]:
        candidate = current + "\n\n" + para
        if len(candidate) <= target:
            current = candidate
        else:
            windows.append(current)
            tail = current[-overlap:] if len(current) > overlap else current
            current = tail + "\n\n" + para

    windows.append(current)
    return windows


def _fallback_chunk(doc: Document, meta: dict[str, Any]) -> Chunk:
    cap = _TARGET_CHARS * 4
    return Chunk(
        chunk_id=f"{doc.doc_id}::full",
        doc_id=doc.doc_id,
        doc_type=doc.doc_type,
        content=doc.content[:cap],
        char_start=0,
        char_end=min(len(doc.content), cap),
        metadata=meta,
    )
