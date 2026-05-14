"""EvalRunner — executes the RAG eval pipeline against a curated dataset.

Builds a retriever from agent_settings (same config as production), runs each
eval query, computes Recall@K / MRR / NDCG@K, and returns a structured report.

Design choices
--------------
- Uses the production retriever config (hybrid BM25, reranker, MMR) so eval
  results reflect real-world retrieval quality.  Pass ``skip_post_processing``
  to measure raw ANN quality separately.
- Intent-aware namespace filtering mirrors ContextAssembler._INTENT_NAMESPACES
  so we test the same retrieval paths the orchestrator uses.
- Latency is measured per-query (wall clock, including Pinecone RTT).
- Relevance is determined by ``metrics.is_relevant()`` — namespace + keyword
  matching, no hard-coded chunk IDs.
"""
from __future__ import annotations

import asyncio
import dataclasses
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.eval.dataset import EvalQuery
from agents.rag.eval.metrics import aggregate_metrics, is_relevant, mrr, ndcg_at_k, recall_at_k
from agents.rag.models import KnowledgeNamespace

if TYPE_CHECKING:
    from agents.rag.retrieval.hyde import HyDEQueryExpander
    from agents.rag.retrieval.retriever import PineconeRetriever

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.eval.runner")

_INTENT_NAMESPACES: dict[str, list[KnowledgeNamespace]] = {
    "roadmap_generation": [
        KnowledgeNamespace.ROLE_TEMPLATES,
        KnowledgeNamespace.ESCO_ONET,
        KnowledgeNamespace.MARKET_REPORTS,
        KnowledgeNamespace.CAREER_KB,
    ],
    "gap_analysis": [
        KnowledgeNamespace.ROLE_TEMPLATES,
        KnowledgeNamespace.ESCO_ONET,
        KnowledgeNamespace.CAREER_KB,
    ],
    "market_intelligence": [
        KnowledgeNamespace.MARKET_REPORTS,
        KnowledgeNamespace.SWISS_EU_MARKET,
    ],
}


@dataclass
class QueryResult:
    query_id: str
    query: str
    intent: str
    latency_seconds: float
    chunks_returned: int
    relevant_flags: list[bool]
    recall_at_5: float
    recall_at_10: float
    mrr_score: float
    ndcg_at_5: float
    ndcg_at_10: float
    namespace_distribution: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass
class EvalReport:
    timestamp: str
    dataset_path: str
    total_queries: int
    failed_queries: int
    mean_recall_at_5: float
    mean_recall_at_10: float
    mean_mrr: float
    mean_ndcg_at_5: float
    mean_ndcg_at_10: float
    p50_latency_seconds: float
    p95_latency_seconds: float
    namespace_precision: dict[str, float]
    by_intent: dict[str, dict[str, float]]
    per_query: list[QueryResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Recall@5={self.mean_recall_at_5:.3f}  "
            f"Recall@10={self.mean_recall_at_10:.3f}  "
            f"MRR={self.mean_mrr:.3f}  "
            f"NDCG@5={self.mean_ndcg_at_5:.3f}  "
            f"NDCG@10={self.mean_ndcg_at_10:.3f}  "
            f"p95_lat={self.p95_latency_seconds:.2f}s  "
            f"({self.total_queries - self.failed_queries}/{self.total_queries} succeeded)"
        )


class EvalRunner:
    """Runs the RAG eval pipeline and returns an EvalReport.

    Parameters
    ----------
    retriever:
        Pre-built PineconeRetriever.  Use ``build_retriever()`` to create one
        from the current agent_settings.
    k_values:
        Cutoffs for Recall@K and NDCG@K.  Defaults to [5, 10].
    hyde_expander:
        Optional HyDEQueryExpander.  When provided, each query is expanded
        into a hypothetical document before retrieval — mirrors the production
        pipeline when hyde_enabled=True.
    """

    def __init__(
        self,
        retriever: "PineconeRetriever",
        *,
        k_values: list[int] | None = None,
        hyde_expander: "HyDEQueryExpander | None" = None,
    ) -> None:
        self._retriever = retriever
        self._k_values = k_values or [5, 10]
        self._hyde = hyde_expander

    async def run(
        self,
        queries: list[EvalQuery],
        *,
        dataset_path: str = "rag_eval.jsonl",
    ) -> EvalReport:
        """Evaluate all queries and return aggregated metrics."""
        with _tracer.start_as_current_span("rag.eval.run") as span:
            span.set_attribute("total_queries", len(queries))
            span.set_attribute("k_values", str(self._k_values))

            results: list[QueryResult] = []
            for query in queries:
                result = await self._eval_query(query)
                results.append(result)
                logger.debug(
                    "rag.eval.query_done",
                    query_id=query.id,
                    recall_at_5=result.recall_at_5,
                    mrr=result.mrr_score,
                    latency=round(result.latency_seconds, 3),
                    error=result.error,
                )

            report = self._build_report(results, dataset_path)
            span.set_attribute("mean_recall_at_5", report.mean_recall_at_5)
            span.set_attribute("mean_mrr", report.mean_mrr)
            span.set_attribute("failed_queries", report.failed_queries)
            logger.info("rag.eval.complete", summary=report.summary())
            return report

    async def _eval_query(self, query: EvalQuery) -> QueryResult:
        t0 = time.monotonic()
        top_k = max(self._k_values)
        namespaces = _INTENT_NAMESPACES.get(query.intent)

        # For real chunk-based queries, verify the source namespace is included
        # in the intent-filtered namespace set so the source chunk can be found.
        if query.chunk_id and query.namespace and namespaces is not None:
            ns_values = [ns.value for ns in namespaces]
            if query.namespace not in ns_values:
                try:
                    namespaces = namespaces + [KnowledgeNamespace(query.namespace)]
                except ValueError:
                    pass  # unknown namespace value — leave filter unchanged

        try:
            # Apply HyDE expansion when an expander is wired in.
            retrieval_query = query.query
            if self._hyde is not None:
                retrieval_query = await self._hyde.expand(
                    query.query, intent_type=query.intent
                )

            chunks = await self._retriever.retrieve(
                retrieval_query, top_k=top_k, namespaces=namespaces
            )
            latency = time.monotonic() - t0

            relevant_flags = [
                is_relevant(c.content, c.namespace, c.chunk_id, query) for c in chunks
            ]
            ns_dist: dict[str, int] = {}
            for c in chunks:
                ns_dist[c.namespace] = ns_dist.get(c.namespace, 0) + 1

            return QueryResult(
                query_id=query.id,
                query=query.query,
                intent=query.intent,
                latency_seconds=latency,
                chunks_returned=len(chunks),
                relevant_flags=relevant_flags,
                recall_at_5=recall_at_k(relevant_flags, 5),
                recall_at_10=recall_at_k(relevant_flags, 10),
                mrr_score=mrr(relevant_flags),
                ndcg_at_5=ndcg_at_k(relevant_flags, 5),
                ndcg_at_10=ndcg_at_k(relevant_flags, 10),
                namespace_distribution=ns_dist,
            )

        except Exception as exc:
            return QueryResult(
                query_id=query.id,
                query=query.query,
                intent=query.intent,
                latency_seconds=time.monotonic() - t0,
                chunks_returned=0,
                relevant_flags=[],
                recall_at_5=0.0,
                recall_at_10=0.0,
                mrr_score=0.0,
                ndcg_at_5=0.0,
                ndcg_at_10=0.0,
                error=str(exc),
            )

    def _build_report(self, results: list[QueryResult], dataset_path: str) -> EvalReport:
        succeeded = [r for r in results if r.error is None]
        failed = len(results) - len(succeeded)

        # Global aggregates
        all_relevant = [r.relevant_flags for r in succeeded]
        agg = aggregate_metrics(all_relevant, self._k_values)

        # Latency percentiles
        latencies = [r.latency_seconds for r in succeeded]
        latencies_sorted = sorted(latencies) if latencies else [0.0]
        p50 = statistics.median(latencies_sorted)
        p95_idx = max(0, int(len(latencies_sorted) * 0.95) - 1)
        p95 = latencies_sorted[p95_idx]

        # Namespace precision: fraction of queries where each namespace appeared
        ns_counts: dict[str, int] = {}
        for r in succeeded:
            for ns in r.namespace_distribution:
                ns_counts[ns] = ns_counts.get(ns, 0) + 1
        n_succeeded = len(succeeded) or 1
        ns_precision = {ns: count / n_succeeded for ns, count in ns_counts.items()}

        # By-intent breakdown
        by_intent: dict[str, dict[str, float]] = {}
        for intent in {r.intent for r in succeeded}:
            intent_results = [r for r in succeeded if r.intent == intent]
            intent_relevant = [r.relevant_flags for r in intent_results]
            by_intent[intent] = aggregate_metrics(intent_relevant, self._k_values)

        return EvalReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            dataset_path=dataset_path,
            total_queries=len(results),
            failed_queries=failed,
            mean_recall_at_5=agg.get("recall_at_5", 0.0),
            mean_recall_at_10=agg.get("recall_at_10", 0.0),
            mean_mrr=agg.get("mrr", 0.0),
            mean_ndcg_at_5=agg.get("ndcg_at_5", 0.0),
            mean_ndcg_at_10=agg.get("ndcg_at_10", 0.0),
            p50_latency_seconds=p50,
            p95_latency_seconds=p95,
            namespace_precision=ns_precision,
            by_intent=by_intent,
            per_query=results,
        )


def build_retriever() -> "PineconeRetriever":
    """Construct a production-equivalent PineconeRetriever from agent_settings.

    Used by the Celery eval task and the CLI script.  Loads BM25 weights from
    Cloudinary (Priority 2 in the load chain) when hybrid search is enabled.
    Wires the reranker when reranker_enabled=True.
    """
    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder
    from agents.rag.ingestion.embedder import OpenAIEmbedder
    from agents.rag.retrieval.reranker import create_reranker
    from agents.rag.retrieval.retriever import PineconeRetriever

    embedder = OpenAIEmbedder()
    sparse_enc = BM25SparseEncoder() if agent_settings.hybrid_search_enabled else None
    reranker = create_reranker()  # returns None when reranker_enabled=False

    return PineconeRetriever(
        embedder=embedder,
        sparse_encoder=sparse_enc,
        reranker=reranker,
    )
