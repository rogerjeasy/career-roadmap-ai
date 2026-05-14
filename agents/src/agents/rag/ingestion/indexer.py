"""Pinecone indexer for the RAG ingestion pipeline.

Upserts EmbeddedChunks into the configured Pinecone serverless index,
routing each chunk to the namespace matching its DocumentType.

Vector record format
  id:            chunk_id
  values:        dense embedding (float list, 3 072 dims)
  sparse_values: BM25 sparse vector {indices, values} — present only when
                 hybrid_search_enabled=True and the chunk carries a
                 sparse_embedding.
  metadata:      doc_id, doc_type, content (≤ 1 000 chars), title,
                 source_url, language, role, industry, country,
                 plus any other scalar extra metadata from the chunk.

Metric note: hybrid search requires ``dotproduct`` metric (not ``cosine``).
When hybrid_search_enabled=True a new index is created with dotproduct.
Existing cosine indexes must be deleted and a new PINECONE_INDEX_NAME set
before enabling hybrid — metric is immutable after index creation.

The ``content`` field is capped at 1 000 chars because Pinecone enforces
a 40 KB metadata limit per vector. Full content is stored in Cloudinary.

If the index does not exist it is created as a serverless index (AWS
us-east-1 by default) on first use.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.models import (
    EmbeddedChunk,
    IndexedChunk,
    KnowledgeNamespace,
    NAMESPACE_FOR_DOC_TYPE,
)
from agents.rag.observability import RAG_UPSERT_DURATION, RAG_UPSERT_TOTAL

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.ingestion.indexer")

_UPSERT_BATCH = 100
_CONTENT_LIMIT = 1000


class PineconeIndexer:
    """Upserts embedded chunks to a Pinecone serverless index."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        index_name: str | None = None,
    ) -> None:
        try:
            from pinecone import Pinecone, ServerlessSpec  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pinecone package is required. "
                "Add it to pyproject.toml: pinecone>=3.0.0"
            ) from exc

        key = api_key or (
            agent_settings.pinecone_api_key.get_secret_value()
            if agent_settings.pinecone_api_key
            else None
        )
        if not key:
            raise RuntimeError(
                "PINECONE_API_KEY is required. "
                "Set it in your environment or .env file."
            )

        self._pc = Pinecone(api_key=key)
        self._index_name = index_name or agent_settings.pinecone_index_name
        self._dimension = agent_settings.pinecone_dimension
        self._ServerlessSpec = ServerlessSpec
        self._index = self._get_or_create_index()

    def _get_or_create_index(self) -> Any:
        existing = [idx.name for idx in self._pc.list_indexes()]
        metric = "dotproduct" if agent_settings.hybrid_search_enabled else "cosine"
        if self._index_name not in existing:
            logger.info(
                "rag.indexer.creating_index",
                index_name=self._index_name,
                dimension=self._dimension,
                metric=metric,
            )
            self._pc.create_index(
                name=self._index_name,
                dimension=self._dimension,
                metric=metric,
                spec=self._ServerlessSpec(
                    cloud=agent_settings.pinecone_cloud,
                    region=agent_settings.pinecone_region,
                ),
            )
        else:
            # Warn if the existing index metric conflicts with the hybrid setting.
            try:
                desc = self._pc.describe_index(self._index_name)
                existing_metric = getattr(desc, "metric", None)
                if agent_settings.hybrid_search_enabled and existing_metric == "cosine":
                    logger.warning(
                        "rag.indexer.metric_mismatch",
                        index=self._index_name,
                        existing_metric="cosine",
                        required_metric="dotproduct",
                        hint="Delete the index and set a new PINECONE_INDEX_NAME to enable hybrid.",
                    )
            except Exception:
                pass
        return self._pc.Index(self._index_name)

    async def upsert(self, chunks: list[EmbeddedChunk]) -> list[IndexedChunk]:
        """Upsert chunks to their respective namespaces concurrently."""
        if not chunks:
            return []

        by_ns: dict[str, list[EmbeddedChunk]] = {}
        for chunk in chunks:
            ns = NAMESPACE_FOR_DOC_TYPE.get(
                chunk.doc_type, KnowledgeNamespace.CAREER_KB
            ).value
            by_ns.setdefault(ns, []).append(chunk)

        results = await asyncio.gather(
            *[
                self._upsert_namespace(ns, ns_chunks)
                for ns, ns_chunks in by_ns.items()
            ]
        )
        return [item for batch in results for item in batch]

    async def _upsert_namespace(
        self, namespace: str, chunks: list[EmbeddedChunk]
    ) -> list[IndexedChunk]:
        indexed: list[IndexedChunk] = []
        for i in range(0, len(chunks), _UPSERT_BATCH):
            batch = chunks[i : i + _UPSERT_BATCH]
            indexed.extend(await self._upsert_batch(namespace, batch))
        return indexed

    async def _upsert_batch(
        self, namespace: str, batch: list[EmbeddedChunk]
    ) -> list[IndexedChunk]:
        vectors = [_build_vector_record(chunk) for chunk in batch]
        with _tracer.start_as_current_span("rag.indexer.upsert_batch") as span:
            span.set_attribute("namespace", namespace)
            span.set_attribute("batch_size", len(vectors))
            t0 = time.monotonic()
            try:
                await asyncio.to_thread(
                    self._index.upsert, vectors=vectors, namespace=namespace
                )
                RAG_UPSERT_DURATION.observe(time.monotonic() - t0)
                RAG_UPSERT_TOTAL.labels(namespace=namespace, status="success").inc()
                logger.info(
                    "rag.indexer.upserted",
                    namespace=namespace,
                    count=len(vectors),
                )
                return [
                    IndexedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        doc_type=chunk.doc_type,
                        namespace=namespace,
                        vector_id=chunk.chunk_id,
                        metadata=chunk.metadata,
                    )
                    for chunk in batch
                ]
            except Exception as exc:
                RAG_UPSERT_DURATION.observe(time.monotonic() - t0)
                RAG_UPSERT_TOTAL.labels(namespace=namespace, status="error").inc()
                logger.error(
                    "rag.indexer.upsert_failed",
                    namespace=namespace,
                    error=str(exc),
                )
                raise


def _build_vector_record(chunk: EmbeddedChunk) -> dict[str, Any]:
    """Build a Pinecone vector record dict.

    Includes ``sparse_values`` only when the chunk carries a sparse_embedding
    (i.e., hybrid_search_enabled and BM25 encoding was performed at ingest).
    """
    record: dict[str, Any] = {
        "id": chunk.chunk_id,
        "values": chunk.embedding,
        "metadata": _build_metadata(chunk),
    }
    if chunk.sparse_embedding is not None:
        record["sparse_values"] = {
            "indices": chunk.sparse_embedding.indices,
            "values": chunk.sparse_embedding.values,
        }
    return record


def _build_metadata(chunk: EmbeddedChunk) -> dict[str, Any]:
    """Build Pinecone metadata (scalar values only; content capped at limit).

    role, industry, and country are promoted explicitly so callers can use
    Pinecone metadata filters without knowing the full metadata schema.
    """
    meta: dict[str, Any] = {
        "doc_id": chunk.doc_id,
        "doc_type": chunk.doc_type.value,
        "content": chunk.content[:_CONTENT_LIMIT],
    }
    for key in ("role", "industry", "country"):
        val = chunk.metadata.get(key)
        if val and isinstance(val, (str, int, float, bool)):
            meta[key] = val
    for k, v in chunk.metadata.items():
        if k not in meta and isinstance(v, (str, int, float, bool)):
            meta[k] = v
    return meta
