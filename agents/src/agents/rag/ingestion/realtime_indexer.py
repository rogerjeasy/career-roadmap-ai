"""Real-time indexing pipeline for single documents or small batches.

This is a lightweight alternative to the Celery-based batch ingestion tasks.
Use it for:
- User CV uploads (must be searchable immediately after upload)
- Freshly scraped market data that cannot wait for the next Celery beat run
- Admin-triggered single-document refreshes

The pipeline is identical to batch ingestion but runs in-process without Celery:
  Document → SemanticChunker → OpenAIEmbedder (+BM25) → PineconeIndexer → list[IndexedChunk]

When ``hybrid_search_enabled=True`` and a ``BM25SparseEncoder`` is supplied (or
auto-created from ``bm25_encoder_path``), each chunk is also sparse-encoded so
the indexer can store hybrid vectors.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from opentelemetry.trace import StatusCode

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.ingestion.chunker import SemanticChunker
from agents.rag.ingestion.embedder import OpenAIEmbedder
from agents.rag.ingestion.indexer import PineconeIndexer
from agents.rag.models import Document, IndexedChunk
from agents.rag.observability import (
    RAG_CHUNKS_CREATED_TOTAL,
    RAG_DOCS_INGESTED_TOTAL,
    RAG_REALTIME_BATCH_FAILURES_TOTAL,
    RAG_REALTIME_INDEX_DURATION,
    RAG_REALTIME_INDEX_TOTAL,
)

if TYPE_CHECKING:
    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.ingestion.realtime_indexer")

_MAX_CONCURRENT = 5


class RealTimeIndexer:
    """Indexes documents immediately without Celery workers.

    All pipeline components are connection-pooled and safe to reuse
    across multiple calls.
    """

    def __init__(
        self,
        *,
        chunker: SemanticChunker | None = None,
        embedder: OpenAIEmbedder | None = None,
        indexer: PineconeIndexer | None = None,
        sparse_encoder: "BM25SparseEncoder | None" = None,
    ) -> None:
        self._chunker = chunker or SemanticChunker()
        self._embedder = embedder or OpenAIEmbedder()
        self._indexer = indexer or PineconeIndexer()

        if sparse_encoder is not None:
            self._sparse_encoder: "BM25SparseEncoder | None" = sparse_encoder
        elif agent_settings.hybrid_search_enabled:
            from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder
            self._sparse_encoder = BM25SparseEncoder(
                params_path=agent_settings.bm25_encoder_path
            )
        else:
            self._sparse_encoder = None

    async def index_document(self, doc: Document) -> list[IndexedChunk]:
        """Chunk, embed, and upsert a single document. Returns the indexed chunks."""
        from opentelemetry.trace import StatusCode  # noqa: PLC0415

        with _tracer.start_as_current_span("rag.realtime.index_document") as span:
            span.set_attribute("doc_id", doc.doc_id)
            span.set_attribute("doc_type", doc.doc_type.value)
            t0 = time.monotonic()

            try:
                chunks = self._chunker.chunk(doc)
                embedded = await self._embedder.embed_chunks(
                    chunks, sparse_encoder=self._sparse_encoder
                )
                indexed = await self._indexer.upsert(embedded)

                elapsed = time.monotonic() - t0
                RAG_DOCS_INGESTED_TOTAL.labels(doc_type=doc.doc_type.value).inc()
                RAG_CHUNKS_CREATED_TOTAL.labels(doc_type=doc.doc_type.value).inc(len(chunks))
                RAG_REALTIME_INDEX_DURATION.labels(doc_type=doc.doc_type.value).observe(elapsed)
                RAG_REALTIME_INDEX_TOTAL.labels(status="success").inc()
                span.set_attribute("chunks", len(indexed))
                span.set_attribute("elapsed_seconds", round(elapsed, 3))
                span.set_status(StatusCode.OK)
                logger.info(
                    "rag.realtime.indexed",
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type.value,
                    chunks=len(indexed),
                    elapsed_seconds=round(elapsed, 3),
                )
                return indexed

            except Exception as exc:
                elapsed = time.monotonic() - t0
                RAG_REALTIME_INDEX_DURATION.labels(doc_type=doc.doc_type.value).observe(elapsed)
                RAG_REALTIME_INDEX_TOTAL.labels(status="error").inc()
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
                logger.error(
                    "rag.realtime.index_failed",
                    doc_id=doc.doc_id,
                    doc_type=doc.doc_type.value,
                    elapsed_seconds=round(elapsed, 3),
                    error=str(exc),
                )
                raise

    async def index_batch(self, docs: list[Document]) -> list[IndexedChunk]:
        """Index multiple documents concurrently (max _MAX_CONCURRENT at a time).

        Partial failures are logged and skipped — successfully indexed chunks
        are still returned. Callers can detect partial failures by comparing
        len(result) against the expected chunk count.
        """
        if not docs:
            return []

        sem = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _bounded(doc: Document) -> list[IndexedChunk]:
            async with sem:
                return await self.index_document(doc)

        results = await asyncio.gather(
            *[_bounded(d) for d in docs],
            return_exceptions=True,
        )

        indexed: list[IndexedChunk] = []
        failed = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed += 1
                RAG_REALTIME_BATCH_FAILURES_TOTAL.inc()
                logger.error(
                    "rag.realtime.batch_item_failed",
                    doc_id=docs[i].doc_id,
                    error=str(result),
                )
            else:
                indexed.extend(result)  # type: ignore[arg-type]

        logger.info(
            "rag.realtime.batch_done",
            total_docs=len(docs),
            failed_docs=failed,
            total_chunks=len(indexed),
        )
        return indexed
