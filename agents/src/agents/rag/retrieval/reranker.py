"""Cross-encoder reranker — second-pass scoring after Pinecone ANN retrieval.

A cross-encoder jointly encodes the query and each candidate passage as a
single sequence, producing a far more precise relevance score than the
approximate cosine similarity returned by the vector database.

Two backends (selected via reranker_type config):

  CrossEncoderReranker — local inference via sentence-transformers.
                         Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
                         (~22 MB, fast CPU inference).
                         Model is loaded lazily on the first call so startup
                         latency is not impacted.
                         Inference runs in asyncio.to_thread (CPU-bound).

  CohereReranker       — cloud inference via Cohere Rerank v3 API.
                         Requires COHERE_API_KEY env var.
                         Supports multilingual model (rerank-multilingual-v3.0).

Both backends:
  - Replace chunk.score with the reranker score (keeps the dataclass immutable
    by constructing new RetrievedChunk instances).
  - Observe Prometheus RAG_RERANK_* metrics.
  - Raise on hard failures; caller (PineconeRetriever) handles graceful
    degradation by catching and falling back to score-sorted order.

Enable with: reranker_enabled=True (default: False — zero overhead when off).
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

from opentelemetry.trace import StatusCode

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.models import RetrievedChunk
from agents.rag.observability import (
    RAG_RERANK_DURATION,
    RAG_RERANK_SCORE,
    RAG_RERANK_TOTAL,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.reranker")


class BaseReranker(ABC):
    """Abstract reranker — takes (query, candidates) → sorted, score-updated candidates."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]: ...


class CrossEncoderReranker(BaseReranker):
    """Local cross-encoder reranker via sentence-transformers.

    Model is loaded from HuggingFace Hub (or local cache) on first call.
    Inference is synchronous/CPU-bound; wrapped in asyncio.to_thread.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or agent_settings.reranker_model
        self._model = None  # lazy — avoids slow startup

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for CrossEncoderReranker. "
                "Add it to pyproject.toml: sentence-transformers>=3.0.0"
            ) from exc
        self._model = CrossEncoder(self._model_name)
        logger.info("rag.reranker.cross_encoder_loaded", model=self._model_name)
        return self._model

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        n = min(top_n or len(chunks), len(chunks))

        with _tracer.start_as_current_span("rag.rerank.cross_encoder") as span:
            span.set_attribute("candidates", len(chunks))
            span.set_attribute("top_n", n)
            t0 = time.monotonic()
            try:
                pairs = [[query, c.content] for c in chunks]
                model = self._load_model()
                raw_scores: list = await asyncio.to_thread(
                    model.predict, pairs, batch_size=32
                )
                scores = [float(s) for s in raw_scores]

                ranked = sorted(
                    zip(scores, chunks), key=lambda x: x[0], reverse=True
                )
                result = [
                    _replace_score(chunk, score) for score, chunk in ranked[:n]
                ]

                duration = time.monotonic() - t0
                RAG_RERANK_DURATION.observe(duration)
                RAG_RERANK_TOTAL.labels(backend="cross_encoder", status="success").inc()
                for chunk in result:
                    RAG_RERANK_SCORE.observe(chunk.score)

                logger.info(
                    "rag.reranker.cross_encoder_done",
                    candidates=len(chunks),
                    returned=len(result),
                    duration_ms=round(duration * 1000),
                )
                return result

            except Exception as exc:
                RAG_RERANK_DURATION.observe(time.monotonic() - t0)
                RAG_RERANK_TOTAL.labels(backend="cross_encoder", status="error").inc()
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR)
                logger.error("rag.reranker.cross_encoder_failed", error=str(exc))
                raise


class CohereReranker(BaseReranker):
    """Cloud-based reranker via Cohere Rerank v3 API.

    Async; no local model download required.
    Supports multilingual documents (use rerank-multilingual-v3.0).
    """

    _DEFAULT_MODEL = "rerank-english-v3.0"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        try:
            import cohere  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "cohere package is required for CohereReranker. "
                "Add it to pyproject.toml: cohere>=5.0.0"
            ) from exc

        key = api_key or (
            agent_settings.cohere_api_key.get_secret_value()
            if agent_settings.cohere_api_key
            else None
        )
        if not key:
            raise RuntimeError(
                "COHERE_API_KEY is required for CohereReranker. "
                "Set it in your environment or .env file."
            )

        self._client = cohere.AsyncClientV2(api_key=key)
        # Do NOT fall back to agent_settings.reranker_model — that's a HuggingFace
        # cross-encoder path, not a valid Cohere model ID.
        self._model = model or self._DEFAULT_MODEL

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        n = min(top_n or len(chunks), len(chunks))

        with _tracer.start_as_current_span("rag.rerank.cohere") as span:
            span.set_attribute("candidates", len(chunks))
            span.set_attribute("top_n", n)
            t0 = time.monotonic()
            try:
                response = await self._client.rerank(
                    model=self._model,
                    query=query,
                    documents=[c.content for c in chunks],
                    top_n=n,
                )

                result = [
                    _replace_score(chunks[r.index], float(r.relevance_score))
                    for r in response.results
                ]

                duration = time.monotonic() - t0
                RAG_RERANK_DURATION.observe(duration)
                RAG_RERANK_TOTAL.labels(backend="cohere", status="success").inc()
                for chunk in result:
                    RAG_RERANK_SCORE.observe(chunk.score)

                logger.info(
                    "rag.reranker.cohere_done",
                    candidates=len(chunks),
                    returned=len(result),
                    duration_ms=round(duration * 1000),
                )
                return result

            except Exception as exc:
                RAG_RERANK_DURATION.observe(time.monotonic() - t0)
                RAG_RERANK_TOTAL.labels(backend="cohere", status="error").inc()
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR)
                logger.error("rag.reranker.cohere_failed", error=str(exc))
                raise


def create_reranker() -> BaseReranker | None:
    """Factory: return the configured reranker instance, or None when disabled."""
    if not agent_settings.reranker_enabled:
        return None
    if agent_settings.reranker_type == "cohere":
        return CohereReranker()
    return CrossEncoderReranker()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _replace_score(chunk: RetrievedChunk, new_score: float) -> RetrievedChunk:
    """Return a new RetrievedChunk with score replaced (dataclass is frozen)."""
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_type=chunk.doc_type,
        content=chunk.content,
        score=new_score,
        namespace=chunk.namespace,
        title=chunk.title,
        source_url=chunk.source_url,
        metadata=chunk.metadata,
    )
