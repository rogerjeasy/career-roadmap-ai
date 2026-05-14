"""Pinecone hybrid (dense + sparse BM25) retriever with optional reranking and MMR.

Retrieval pipeline (each stage is opt-in via config):

  1. Embed — query → dense vector (OpenAI text-embedding-3-large).
  2. Sparse encode — query → BM25 sparse vector (only when hybrid=True).
  3. Fan-out — concurrent Pinecone ANN queries across all configured namespaces.
             Fetches fetch_k = top_k × fetch_k_multiplier candidates per ns
             when reranker or MMR is enabled; otherwise fetches exactly top_k.
  4. Merge — flatten all namespace results, sort by score descending.
  5. Filter — apply min_score threshold + doc_id deduplication.
  6. Rerank (optional) — cross-encoder or Cohere re-scores the candidates for
             higher precision. Replaces Pinecone cosine/hybrid scores.
  7. MMR (optional) — Maximal Marginal Relevance diversifies the reranked set
             by fetching stored Pinecone vectors and running greedy selection.
  8. Trim — return the final top_k chunks.

When reranker_enabled=False and mmr_enabled=False the pipeline reduces to the
original dense/hybrid retrieval with no added latency.

Per-namespace alpha defaults (lower = more keyword-precise):
  taxonomy        0.50 — ESCO/O*NET codes need exact term matching
  role-templates  0.65 — job titles benefit from keyword precision
  swiss-eu-market 0.60 — location/legal terms need exact matching
  career-kb       0.75 — balanced; articles mix concepts + jargon
  market-reports  0.80 — conceptual queries dominate
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from opentelemetry.trace import StatusCode

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.ingestion.embedder import OpenAIEmbedder
from agents.rag.models import KnowledgeNamespace, RetrievedChunk, SparseVector
from agents.rag.observability import (
    RAG_CHUNKS_RETRIEVED,
    RAG_PIPELINE_STAGE,
    RAG_QUERY_DURATION,
    RAG_QUERY_TOTAL,
    RAG_RETRIEVAL_SCORE,
)
from agents.rag.retrieval.mmr import apply_mmr

if TYPE_CHECKING:
    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder
    from agents.rag.retrieval.reranker import BaseReranker

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.retriever")

# Per-namespace alpha: weight given to the dense vector (1-alpha → sparse weight).
_NAMESPACE_ALPHA: dict[str, float] = {
    KnowledgeNamespace.ESCO_ONET.value: 0.50,
    KnowledgeNamespace.ROLE_TEMPLATES.value: 0.65,
    KnowledgeNamespace.SWISS_EU_MARKET.value: 0.60,
    KnowledgeNamespace.CAREER_KB.value: 0.75,
    KnowledgeNamespace.MARKET_REPORTS.value: 0.80,
}


class PineconeRetriever:
    """Retrieves relevant chunks from Pinecone with optional reranking and MMR.

    Supports dense-only, hybrid (dense + BM25 sparse), cross-encoder reranking,
    and MMR diversity filtering.  All post-processing stages are opt-in via
    config flags so the class degrades gracefully to pure ANN retrieval when
    they are disabled.
    """

    def __init__(
        self,
        *,
        embedder: OpenAIEmbedder,
        sparse_encoder: "BM25SparseEncoder | None" = None,
        reranker: "BaseReranker | None" = None,
        api_key: str | None = None,
        index_name: str | None = None,
        namespaces: list[KnowledgeNamespace] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
        alpha: float | None = None,
        mmr_enabled: bool | None = None,
        mmr_lambda: float | None = None,
        fetch_k_multiplier: int | None = None,
        dedup_by_doc: bool = True,
    ) -> None:
        try:
            from pinecone import Pinecone  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pinecone package is required. Add it to pyproject.toml: pinecone>=3.0.0"
            ) from exc

        key = api_key or (
            agent_settings.pinecone_api_key.get_secret_value()
            if agent_settings.pinecone_api_key
            else None
        )
        if not key:
            raise RuntimeError("PINECONE_API_KEY is required.")

        self._embedder = embedder
        self._sparse_encoder = sparse_encoder
        self._hybrid = agent_settings.hybrid_search_enabled and sparse_encoder is not None
        self._default_alpha = alpha if alpha is not None else agent_settings.hybrid_alpha
        self._index = Pinecone(api_key=key).Index(
            index_name or agent_settings.pinecone_index_name
        )
        self._namespaces = namespaces or list(KnowledgeNamespace)
        self._top_k = top_k or agent_settings.rag_top_k
        self._min_score = min_score if min_score is not None else agent_settings.rag_min_score

        # Post-processing stages
        self._reranker = reranker
        self._reranker_top_n = agent_settings.reranker_top_n
        self._mmr_enabled = (
            mmr_enabled if mmr_enabled is not None else agent_settings.mmr_enabled
        )
        self._mmr_lambda = (
            mmr_lambda if mmr_lambda is not None else agent_settings.mmr_lambda
        )
        self._fetch_k_multiplier = (
            fetch_k_multiplier
            if fetch_k_multiplier is not None
            else agent_settings.fetch_k_multiplier
        )
        self._dedup_by_doc = dedup_by_doc

    # ── Public interface ──────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        namespaces: list[KnowledgeNamespace] | None = None,
    ) -> list[RetrievedChunk]:
        """Return top_k diverse, high-precision chunks for ``query``.

        Applies reranking and/or MMR when the corresponding config flags are on.
        The entire pipeline — ANN fan-out, reranking, and MMR — runs under a
        single ``rag.retrieve`` OTel span so all child spans are properly nested.
        """
        k = top_k or self._top_k
        ns_list = namespaces or self._namespaces
        post_processing = bool(self._reranker or self._mmr_enabled)
        fetch_k = k * self._fetch_k_multiplier if post_processing else k

        with _tracer.start_as_current_span("rag.retrieve") as span:
            span.set_attribute("query_length", len(query))
            span.set_attribute("top_k", k)
            span.set_attribute("fetch_k", fetch_k)
            span.set_attribute("hybrid", self._hybrid)
            span.set_attribute("reranker_enabled", self._reranker is not None)
            span.set_attribute("mmr_enabled", self._mmr_enabled)

            # ── ANN fan-out ───────────────────────────────────────────────────
            dense_embedding = await self._embedder.embed_query(query)

            sparse_vector: SparseVector | None = None
            if self._hybrid and self._sparse_encoder is not None:
                sparse_vector = self._sparse_encoder.encode_query(query)

            results_per_ns = await asyncio.gather(
                *[
                    self._query_namespace(dense_embedding, sparse_vector, ns, fetch_k)
                    for ns in ns_list
                ],
                return_exceptions=True,
            )
            RAG_PIPELINE_STAGE.labels(stage="ann", status="success").inc()

            candidates = self._merge_and_filter(results_per_ns, fetch_k)
            span.set_attribute("candidates_after_filter", len(candidates))

            # ── Stage 1: Reranking ────────────────────────────────────────────
            if self._reranker and candidates:
                rerank_n = self._reranker_top_n or fetch_k
                try:
                    candidates = await self._reranker.rerank(
                        query, candidates, top_n=rerank_n
                    )
                    RAG_PIPELINE_STAGE.labels(stage="rerank", status="success").inc()
                except Exception as exc:
                    RAG_PIPELINE_STAGE.labels(stage="rerank", status="error").inc()
                    span.record_exception(exc)
                    logger.warning(
                        "rag.retriever.rerank_failed_using_score_order",
                        error=str(exc),
                    )
            else:
                RAG_PIPELINE_STAGE.labels(stage="rerank", status="skipped").inc()

            # ── Stage 2: MMR diversity filter ─────────────────────────────────
            if self._mmr_enabled and len(candidates) > k:
                candidates = await apply_mmr(
                    self._index,
                    dense_embedding,
                    candidates,
                    top_k=k,
                    lambda_mult=self._mmr_lambda,
                )
                RAG_PIPELINE_STAGE.labels(stage="mmr", status="success").inc()
            else:
                RAG_PIPELINE_STAGE.labels(stage="mmr", status="skipped").inc()

            # ── Final trim ────────────────────────────────────────────────────
            final = candidates[:k]
            span.set_attribute("chunks_returned", len(final))

            for chunk in final:
                RAG_RETRIEVAL_SCORE.observe(chunk.score)
            RAG_CHUNKS_RETRIEVED.observe(len(final))

            logger.info(
                "rag.retriever.done",
                query_length=len(query),
                chunks_returned=len(final),
                hybrid=self._hybrid,
                reranked=self._reranker is not None,
                mmr=self._mmr_enabled,
            )
            return final

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _merge_and_filter(
        self,
        results_per_ns: tuple,
        cap: int,
    ) -> list[RetrievedChunk]:
        """Merge namespace results, sort by score, apply min_score + doc dedup."""
        all_chunks: list[RetrievedChunk] = []
        for result in results_per_ns:
            if isinstance(result, Exception):
                logger.warning("rag.retriever.namespace_failed", error=str(result))
                continue
            all_chunks.extend(result)  # type: ignore[arg-type]

        all_chunks.sort(key=lambda c: c.score, reverse=True)

        seen_docs: set[str] = set()
        filtered: list[RetrievedChunk] = []
        for chunk in all_chunks:
            if chunk.score < self._min_score:
                continue
            if self._dedup_by_doc:
                if chunk.doc_id in seen_docs:
                    continue
                seen_docs.add(chunk.doc_id)
            filtered.append(chunk)
            if len(filtered) >= cap:
                break

        return filtered

    async def _query_namespace(
        self,
        dense_embedding: list[float],
        sparse_vector: SparseVector | None,
        namespace: KnowledgeNamespace,
        top_k: int,
    ) -> list[RetrievedChunk]:
        ns = namespace.value
        t0 = time.monotonic()
        with _tracer.start_as_current_span("rag.query_namespace") as ns_span:
            ns_span.set_attribute("namespace", ns)
            ns_span.set_attribute("top_k", top_k)
            ns_span.set_attribute("hybrid", self._hybrid)
            try:
                query_kwargs: dict = {
                    "top_k": top_k,
                    "namespace": ns,
                    "include_metadata": True,
                }

                if self._hybrid and sparse_vector is not None:
                    alpha = _NAMESPACE_ALPHA.get(ns, self._default_alpha)
                    scaled_dense, scaled_sparse = _scale_hybrid(
                        dense_embedding, sparse_vector, alpha
                    )
                    query_kwargs["vector"] = scaled_dense
                    query_kwargs["sparse_vector"] = scaled_sparse
                else:
                    query_kwargs["vector"] = dense_embedding

                response = await asyncio.to_thread(self._index.query, **query_kwargs)
                RAG_QUERY_DURATION.observe(time.monotonic() - t0)
                RAG_QUERY_TOTAL.labels(namespace=ns, status="success").inc()

                chunks: list[RetrievedChunk] = []
                for match in response.matches:
                    meta = match.metadata or {}
                    chunks.append(
                        RetrievedChunk(
                            chunk_id=match.id,
                            doc_id=str(meta.get("doc_id", match.id)),
                            doc_type=str(meta.get("doc_type", "")),
                            content=str(meta.get("content", "")),
                            score=float(match.score),
                            namespace=ns,
                            title=str(meta.get("title", "")),
                            source_url=meta.get("source_url") or None,
                            metadata=meta,
                        )
                    )
                ns_span.set_attribute("chunks_returned", len(chunks))
                ns_span.set_status(StatusCode.OK)
                return chunks

            except Exception as exc:
                RAG_QUERY_DURATION.observe(time.monotonic() - t0)
                RAG_QUERY_TOTAL.labels(namespace=ns, status="error").inc()
                ns_span.record_exception(exc)
                ns_span.set_status(StatusCode.ERROR, str(exc))
                logger.warning("rag.retriever.query_failed", namespace=ns, error=str(exc))
                raise


def _scale_hybrid(
    dense: list[float],
    sparse: SparseVector,
    alpha: float,
) -> tuple[list[float], dict[str, list]]:
    """Pre-scale dense and sparse vectors for Pinecone hybrid score combination.

    Pinecone's combined score = alpha * dense_score + (1-alpha) * sparse_score.
    This is achieved by scaling the vectors before submission.
    """
    scaled_dense = [v * alpha for v in dense]
    scaled_sparse = {
        "indices": sparse.indices,
        "values": [v * (1.0 - alpha) for v in sparse.values],
    }
    return scaled_dense, scaled_sparse
