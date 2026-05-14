"""Retrieval quality metrics for the RAG eval pipeline.

All functions accept a ``relevant`` sequence of booleans where
``relevant[i]`` is True when the i-th retrieved chunk is relevant to the query.
The order mirrors the retriever's ranked output (highest score first).

Metric definitions
------------------
Recall@K
    Binary: 1.0 if at least one relevant chunk appears in the top-K results,
    0.0 otherwise.  Measures whether the answer exists in the retrieved set.

MRR (Mean Reciprocal Rank)
    1 / rank of the first relevant chunk.  Rewards having the best result at
    the top.  Returns 0.0 when no relevant chunk is found.

NDCG@K (Normalized Discounted Cumulative Gain)
    Uses binary relevance (0/1).  DCG@K discounts each hit by log2(rank+1).
    Normalised against the ideal DCG (all relevant items at the top).
    Returns 0.0 when no relevant chunks exist in the full result list.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from agents.rag.eval.dataset import EvalQuery


def recall_at_k(relevant: Sequence[bool], k: int) -> float:
    """Return 1.0 if any of the first ``k`` results is relevant, else 0.0."""
    return 1.0 if any(relevant[:k]) else 0.0


def mrr(relevant: Sequence[bool]) -> float:
    """Return 1/(rank of first relevant result). 0.0 if none found."""
    for i, r in enumerate(relevant):
        if r:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(relevant: Sequence[bool], k: int) -> float:
    """Discounted Cumulative Gain at K with binary relevance scores."""
    return sum(
        float(rel) / math.log2(i + 2)
        for i, rel in enumerate(relevant[:k])
    )


def ndcg_at_k(relevant: Sequence[bool], k: int) -> float:
    """Normalized DCG at K. Returns 0.0 when no relevant chunks exist."""
    actual = dcg_at_k(relevant, k)
    if actual == 0.0:
        return 0.0
    n_relevant = sum(1 for r in relevant if r)
    ideal = dcg_at_k([True] * min(n_relevant, k), k)
    return actual / ideal if ideal > 0.0 else 0.0


def is_relevant(content: str, namespace: str, chunk_id: str, query: "EvalQuery") -> bool:
    """Return True when a retrieved chunk satisfies the eval query's relevance criteria.

    Two modes, selected automatically based on which fields are populated:

    Real query (``query.chunk_id`` is set):
        Exact Pinecone chunk_id match.  The source chunk must appear in the
        retrieved list.  Strictest possible ground truth — no guessing.

    Synthetic query (``query.expected_namespaces`` is set, legacy fallback):
        Namespace membership + keyword threshold match.
        Used only for the hand-crafted ``rag_eval.jsonl`` queries.
    """
    if query.chunk_id:
        return chunk_id == query.chunk_id
    # Legacy keyword-based relevance for synthetic queries.
    if namespace not in query.expected_namespaces:
        return False
    if not query.expected_keywords:
        return True
    content_lower = content.lower()
    hits = sum(1 for kw in query.expected_keywords if kw.lower() in content_lower)
    return hits >= query.min_keyword_hits


def aggregate_metrics(
    per_query_relevant: list[list[bool]],
    k_values: list[int],
) -> dict[str, float]:
    """Compute mean Recall@K, MRR, and NDCG@K across all queries.

    Returns a flat dict keyed by metric name, e.g.
    ``{"recall_at_5": 0.82, "recall_at_10": 0.91, "mrr": 0.61, ...}``.
    """
    if not per_query_relevant:
        return {}

    result: dict[str, float] = {}
    n = len(per_query_relevant)

    for k in k_values:
        result[f"recall_at_{k}"] = sum(
            recall_at_k(r, k) for r in per_query_relevant
        ) / n
        result[f"ndcg_at_{k}"] = sum(
            ndcg_at_k(r, k) for r in per_query_relevant
        ) / n

    result["mrr"] = sum(mrr(r) for r in per_query_relevant) / n
    return result
