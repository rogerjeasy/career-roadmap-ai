"""OpenAI embedder for the RAG ingestion and retrieval pipelines.

Uses ``text-embedding-3-large`` (3 072-dimensional dotproduct-space vectors)
via the ``openai`` Python SDK. When a ``BM25SparseEncoder`` is supplied, each
``EmbeddedChunk`` is also populated with a ``sparse_embedding`` for hybrid
Pinecone upserts.

Graceful degradation:
- ImportError at construction if ``openai`` is not installed.
- RuntimeError at construction if OPENAI_API_KEY is absent.
- Never returns partial results — raises on API error so the caller
  can decide whether to retry or skip the batch.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.models import Chunk, EmbeddedChunk
from agents.rag.observability import RAG_EMBED_DURATION, RAG_EMBED_TOKENS_TOTAL, RAG_EMBED_TOTAL

if TYPE_CHECKING:
    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.ingestion.embedder")


class OpenAIEmbedder:
    """Embeds chunks and queries using OpenAI ``text-embedding-3-large``.

    One instance per process; ``openai.AsyncOpenAI`` handles connection pooling.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openai package is required for embedding. "
                "Add it to pyproject.toml: openai>=1.0.0"
            ) from exc

        key = api_key or (
            agent_settings.openai_api_key.get_secret_value()
            if agent_settings.openai_api_key
            else None
        )
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for embedding. "
                "Set it in your environment or .env file."
            )

        self._client = AsyncOpenAI(api_key=key)
        self._model = model or agent_settings.embedding_model
        self._batch_size = batch_size or agent_settings.embedding_batch_size

    async def embed_chunks(
        self,
        chunks: list[Chunk],
        *,
        sparse_encoder: "BM25SparseEncoder | None" = None,
    ) -> list[EmbeddedChunk]:
        """Embed a list of chunks in batches. Preserves input order.

        When ``sparse_encoder`` is provided each returned ``EmbeddedChunk``
        carries a ``sparse_embedding`` for hybrid Pinecone upserts.
        """
        if not chunks:
            return []
        embedded: list[EmbeddedChunk] = []
        for i in range(0, len(chunks), self._batch_size):
            batch = chunks[i : i + self._batch_size]
            embedded.extend(await self._embed_batch(batch, sparse_encoder=sparse_encoder))
        return embedded

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for similarity retrieval."""
        with _tracer.start_as_current_span("rag.embed_query"):
            t0 = time.monotonic()
            try:
                response = await self._client.embeddings.create(
                    input=[text], model=self._model
                )
                RAG_EMBED_DURATION.observe(time.monotonic() - t0)
                RAG_EMBED_TOTAL.labels(status="success").inc()
                if response.usage:
                    RAG_EMBED_TOKENS_TOTAL.labels(mode="query").inc(response.usage.total_tokens)
                return response.data[0].embedding
            except Exception as exc:
                RAG_EMBED_DURATION.observe(time.monotonic() - t0)
                RAG_EMBED_TOTAL.labels(status="error").inc()
                logger.error("rag.embedder.query_failed", error=str(exc))
                raise

    async def _embed_batch(
        self,
        chunks: list[Chunk],
        *,
        sparse_encoder: "BM25SparseEncoder | None" = None,
    ) -> list[EmbeddedChunk]:
        texts = [c.content for c in chunks]
        with _tracer.start_as_current_span("rag.embed_batch") as span:
            span.set_attribute("batch_size", len(texts))
            span.set_attribute("hybrid", sparse_encoder is not None)
            t0 = time.monotonic()
            try:
                response = await self._client.embeddings.create(
                    input=texts, model=self._model
                )
                RAG_EMBED_DURATION.observe(time.monotonic() - t0)
                RAG_EMBED_TOTAL.labels(status="success").inc()
                if response.usage:
                    RAG_EMBED_TOKENS_TOTAL.labels(mode="batch").inc(response.usage.total_tokens)
                logger.info(
                    "rag.embedder.batch_done",
                    batch_size=len(texts),
                    model=self._model,
                    tokens=response.usage.total_tokens if response.usage else 0,
                    hybrid=sparse_encoder is not None,
                )
                ordered = sorted(response.data, key=lambda item: item.index)

                sparse_vectors = (
                    sparse_encoder.encode_documents(texts)
                    if sparse_encoder is not None
                    else [None] * len(chunks)
                )

                return [
                    EmbeddedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        doc_type=chunk.doc_type,
                        content=chunk.content,
                        embedding=item.embedding,
                        sparse_embedding=sv,
                        metadata=chunk.metadata,
                    )
                    for chunk, item, sv in zip(chunks, ordered, sparse_vectors)
                ]
            except Exception as exc:
                RAG_EMBED_DURATION.observe(time.monotonic() - t0)
                RAG_EMBED_TOTAL.labels(status="error").inc()
                logger.error(
                    "rag.embedder.batch_failed",
                    batch_size=len(texts),
                    error=str(exc),
                )
                raise
