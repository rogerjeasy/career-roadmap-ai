"""Maximal Marginal Relevance (MMR) diversity filter.

MMR balances relevance and diversity in the final chunk selection so that
the returned passages cover different aspects of the query rather than
all being near-duplicates of the top-1 hit.

Algorithm (greedy, O(n²) for n candidates):

  score(d) = λ × sim(d, query) − (1−λ) × max(sim(d, d_i) for d_i in selected)

  λ = 1.0 → pure relevance (same ordering as score-sorted Pinecone results)
  λ = 0.0 → maximum diversity
  λ = 0.5 → balanced default (recommended)

At each step the candidate with the highest MMR score is added to the
result set and removed from the candidate pool.  The redundancy term is
updated for the next iteration.

Vector sourcing:
  Stored Pinecone embeddings are retrieved via index.fetch() per namespace.
  This avoids a secondary OpenAI embedding API call on the already-retrieved
  chunks.  Pinecone stores the original dense vector alongside each record's
  metadata, so the fetch round-trip is cheap (single gRPC call per namespace).

Graceful degradation:
  Chunks whose vector could not be fetched are appended to the selection
  in their original score-sorted order after MMR has filled as many slots
  as possible with vectorised candidates.  The function never raises.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from opentelemetry.trace import StatusCode

from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.models import RetrievedChunk
from agents.rag.observability import (
    RAG_MMR_DURATION,
    RAG_MMR_TOTAL,
    RAG_MMR_VECTOR_COVERAGE,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.mmr")


# ── Pure algorithm ────────────────────────────────────────────────────────────


def _dot(a: list[float], b: list[float]) -> float:
    """Dot product of two equal-length vectors.

    Pinecone normalises stored vectors to unit length when the index metric is
    ``dotproduct``, so dot product equals cosine similarity here.
    """
    return sum(x * y for x, y in zip(a, b))


def maximal_marginal_relevance(
    query_embedding: list[float],
    chunk_vectors: dict[str, list[float]],
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    lambda_mult: float = 0.5,
) -> list[RetrievedChunk]:
    """Greedy MMR selection.

    Parameters
    ----------
    query_embedding:
        Dense vector for the query (same space as stored chunk vectors).
    chunk_vectors:
        Mapping chunk_id → L2-normalised dense embedding fetched from Pinecone.
        Chunks absent from this dict are treated as fallback (appended last).
    candidates:
        Pre-sorted by relevance score (highest first).  Only candidates in this
        list are eligible for selection.
    top_k:
        Maximum number of chunks to return.
    lambda_mult:
        λ in the MMR formula.  0.5 is a good default.
    """
    if not candidates or top_k <= 0:
        return candidates[:top_k]

    with_vec = [c for c in candidates if c.chunk_id in chunk_vectors]
    no_vec = [c for c in candidates if c.chunk_id not in chunk_vectors]

    if not with_vec:
        # No vectors available — return score-sorted order unchanged
        return candidates[:top_k]

    selected: list[RetrievedChunk] = []
    selected_vecs: list[list[float]] = []
    remaining = list(with_vec)

    while remaining and len(selected) < top_k:
        best_chunk: RetrievedChunk | None = None
        best_mmr = -math.inf

        for chunk in remaining:
            vec = chunk_vectors[chunk.chunk_id]
            relevance = _dot(query_embedding, vec)

            if not selected_vecs:
                mmr_score = relevance
            else:
                redundancy = max(_dot(vec, sv) for sv in selected_vecs)
                mmr_score = lambda_mult * relevance - (1.0 - lambda_mult) * redundancy

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_chunk = chunk

        if best_chunk is None:
            break

        selected.append(best_chunk)
        selected_vecs.append(chunk_vectors[best_chunk.chunk_id])
        remaining.remove(best_chunk)

    # Append fallback chunks (no stored vector) to fill any remaining slots
    slots_left = top_k - len(selected)
    if slots_left > 0:
        selected.extend(no_vec[:slots_left])

    return selected


# ── I/O: fetch vectors from Pinecone ─────────────────────────────────────────


async def fetch_chunk_vectors(
    index: Any,
    chunks: list[RetrievedChunk],
) -> dict[str, list[float]]:
    """Fetch stored Pinecone embeddings for a list of retrieved chunks.

    Groups chunk IDs by namespace, issues concurrent index.fetch() calls,
    and returns a flat dict of chunk_id → embedding vector.

    Missing IDs are silently omitted (caller handles graceful degradation).
    """
    by_namespace: dict[str, list[str]] = {}
    for c in chunks:
        by_namespace.setdefault(c.namespace, []).append(c.chunk_id)

    vectors: dict[str, list[float]] = {}

    async def _fetch_ns(ns: str, ids: list[str]) -> None:
        try:
            result = await asyncio.to_thread(index.fetch, ids=ids, namespace=ns)
            ns_vectors = getattr(result, "vectors", {}) or {}
            for vid, vdata in ns_vectors.items():
                values = getattr(vdata, "values", None)
                if values:
                    vectors[vid] = list(values)
        except Exception as exc:
            logger.warning(
                "rag.mmr.fetch_vectors_failed",
                namespace=ns,
                count=len(ids),
                error=str(exc),
            )

    await asyncio.gather(*[_fetch_ns(ns, ids) for ns, ids in by_namespace.items()])

    logger.debug(
        "rag.mmr.vectors_fetched",
        requested=len(chunks),
        retrieved=len(vectors),
    )
    return vectors


# ── High-level entry point ────────────────────────────────────────────────────


async def apply_mmr(
    index: Any,
    query_embedding: list[float],
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    lambda_mult: float = 0.5,
) -> list[RetrievedChunk]:
    """Fetch vectors and run MMR; falls back to score-sorted order on any error.

    This is the single entry point called by PineconeRetriever.
    """
    with _tracer.start_as_current_span("rag.mmr") as span:
        span.set_attribute("candidates", len(candidates))
        span.set_attribute("top_k", top_k)
        span.set_attribute("lambda_mult", lambda_mult)
        t0 = time.monotonic()
        try:
            vectors = await fetch_chunk_vectors(index, candidates)

            # Coverage ratio: what fraction of candidates had a stored vector.
            # < 1.0 means MMR will fall back to score order for some chunks.
            coverage = len(vectors) / len(candidates) if candidates else 1.0
            RAG_MMR_VECTOR_COVERAGE.observe(coverage)
            span.set_attribute("vector_coverage", round(coverage, 3))

            result = maximal_marginal_relevance(
                query_embedding,
                vectors,
                candidates,
                top_k=top_k,
                lambda_mult=lambda_mult,
            )
            duration = time.monotonic() - t0
            RAG_MMR_DURATION.observe(duration)
            RAG_MMR_TOTAL.labels(status="success").inc()
            logger.info(
                "rag.mmr.done",
                candidates=len(candidates),
                selected=len(result),
                vectors_fetched=len(vectors),
                vector_coverage=round(coverage, 3),
                lambda_mult=lambda_mult,
                duration_ms=round(duration * 1000),
            )
            return result
        except Exception as exc:
            RAG_MMR_DURATION.observe(time.monotonic() - t0)
            RAG_MMR_TOTAL.labels(status="error").inc()
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            logger.warning("rag.mmr.failed_using_score_order", error=str(exc))
            return candidates[:top_k]
