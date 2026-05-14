#!/usr/bin/env python
"""CLI for running the offline RAG evaluation pipeline.

Usage
-----
    cd agents
    poetry run python scripts/eval_rag.py
    poetry run python scripts/eval_rag.py --k 5 10 --output results.json
    poetry run python scripts/eval_rag.py --dataset data/eval/rag_eval.jsonl --push-metrics

Options
-------
--dataset PATH      Path to the JSONL eval dataset.
                    Default: agents/data/eval/rag_eval.jsonl
--k INT [INT ...]   Cutoffs for Recall@K and NDCG@K. Default: 5 10
--output PATH       Write the full JSON report to this path.
--push-metrics      Push results to Prometheus Pushgateway (requires
                    PROMETHEUS_PUSHGATEWAY_URL env var).
--no-reranker       Skip cross-encoder reranking (faster, measures raw ANN).
--no-mmr            Skip MMR diversity filter.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time

# Ensure the agents package is importable when running from the agents/ dir.
_AGENTS_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _AGENTS_SRC not in sys.path:
    sys.path.insert(0, _AGENTS_SRC)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RAG offline evaluation pipeline")
    p.add_argument("--dataset", default=None, help="Path to JSONL eval dataset")
    p.add_argument("--k", nargs="+", type=int, default=[5, 10], metavar="K")
    p.add_argument("--output", default=None, help="Write JSON report to this file")
    p.add_argument(
        "--push-metrics",
        action="store_true",
        help="Push Gauge metrics to Prometheus Pushgateway",
    )
    p.add_argument(
        "--no-reranker",
        action="store_true",
        help="Disable reranking entirely (measures raw ANN + fetch_k quality).",
    )
    p.add_argument(
        "--reranker",
        choices=["auto", "cross_encoder", "cohere"],
        default="auto",
        help=(
            "Reranker backend to use (default: auto = read from agent_settings). "
            "'cross_encoder' forces local MiniLM. "
            "'cohere' forces Cohere Rerank v3 (requires COHERE_API_KEY)."
        ),
    )
    p.add_argument(
        "--hyde",
        action="store_true",
        help="Enable HyDE query expansion before retrieval. "
             "Generates a hypothetical document per query using Claude Haiku. "
             "Adds ~0.5s per query but improves recall on vague/structured-data queries.",
    )
    p.add_argument(
        "--no-mmr",
        action="store_true",
        help="Disable MMR diversity filter",
    )
    p.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help=(
            "Min score threshold passed to the retriever (default: 0.0 for eval). "
            "Production default is 0.65 but hybrid scaling reduces scores; "
            "use 0.0 here to measure unfiltered top-K recall."
        ),
    )
    p.add_argument(
        "--no-dedup",
        action="store_true",
        default=True,
        help=(
            "Disable doc-ID deduplication in the retriever (default: True for eval). "
            "Production dedup keeps only the top chunk per doc; eval needs every chunk "
            "so the specific source chunk_id can be found."
        ),
    )
    return p.parse_args()


async def _main(args: argparse.Namespace) -> None:
    from agents.config import agent_settings
    from agents.rag.eval.dataset import load_eval_dataset
    from agents.rag.eval.runner import EvalRunner
    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder
    from agents.rag.ingestion.embedder import OpenAIEmbedder
    from agents.rag.retrieval.reranker import create_reranker
    from agents.rag.retrieval.retriever import PineconeRetriever

    print(f"Loading eval dataset from: {args.dataset or 'default (rag_eval.jsonl)'}")
    queries = load_eval_dataset(args.dataset)
    print(f"  {len(queries)} queries loaded")

    # Build retriever — honour CLI flags to skip post-processing stages.
    embedder = OpenAIEmbedder()
    sparse_enc = BM25SparseEncoder() if agent_settings.hybrid_search_enabled else None
    # Reranker: --no-reranker disables entirely; --reranker selects backend.
    # Default "auto" reads from agent_settings; if disabled there, falls back to
    # CrossEncoder so eval always tests reranking unless explicitly skipped.
    if args.no_reranker:
        reranker = None
    elif args.reranker == "cohere":
        from agents.rag.retrieval.reranker import CohereReranker  # noqa: PLC0415
        reranker = CohereReranker()
    elif args.reranker == "cross_encoder":
        from agents.rag.retrieval.reranker import CrossEncoderReranker  # noqa: PLC0415
        reranker = CrossEncoderReranker()
    else:  # auto
        reranker = create_reranker()  # respects config
        if reranker is None:
            # Config has reranker disabled — still test with CrossEncoder for eval.
            from agents.rag.retrieval.reranker import CrossEncoderReranker  # noqa: PLC0415
            reranker = CrossEncoderReranker()
    retriever = PineconeRetriever(
        embedder=embedder,
        sparse_encoder=sparse_enc,
        reranker=reranker,
        mmr_enabled=False if args.no_mmr else None,
        min_score=args.min_score,
        dedup_by_doc=not args.no_dedup,
    )

    # HyDE: create expander only when --hyde is passed (adds ~0.5s/query).
    hyde_expander = None
    if args.hyde:
        from agents.rag.retrieval.hyde import get_hyde_expander  # noqa: PLC0415
        hyde_expander = get_hyde_expander()
        print("  HyDE expansion enabled (claude-haiku per query)")

    runner = EvalRunner(retriever, k_values=args.k, hyde_expander=hyde_expander)

    if args.no_reranker:
        reranker_label = "off"
    elif reranker is None:
        reranker_label = "off (disabled in config)"
    elif args.reranker == "cohere":
        reranker_label = "on (cohere rerank-english-v3.0)"
    elif args.reranker == "cross_encoder":
        reranker_label = f"on (cross_encoder {agent_settings.reranker_model})"
    else:
        reranker_label = f"on ({type(reranker).__name__})"
    dedup_label = "off" if args.no_dedup else "on"
    print(
        f"\nRunning eval (k={args.k}, min_score={args.min_score}, "
        f"dedup={dedup_label}, reranker={reranker_label}, "
        f"hyde={'on' if args.hyde else 'off'}, "
        f"mmr={'off' if args.no_mmr else 'on'}) ..."
    )
    t0 = time.monotonic()
    report = await runner.run(queries, dataset_path=args.dataset or "rag_eval.jsonl")
    elapsed = time.monotonic() - t0

    # ── Print summary table ──────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("RAG Eval Results")
    print(f"{'─' * 60}")
    print(f"  Total queries   : {report.total_queries}  (failed: {report.failed_queries})")
    print(f"  Eval wall time  : {elapsed:.1f}s")
    print(f"  p50 latency     : {report.p50_latency_seconds:.3f}s")
    print(f"  p95 latency     : {report.p95_latency_seconds:.3f}s")
    print(f"{'─' * 60}")
    for k in args.k:
        recall = getattr(report, f"mean_recall_at_{k}", None)
        ndcg = getattr(report, f"mean_ndcg_at_{k}", None)
        if recall is not None:
            print(f"  Recall@{k:<2}        : {recall:.4f}")
        if ndcg is not None:
            print(f"  NDCG@{k:<2}          : {ndcg:.4f}")
    print(f"  MRR             : {report.mean_mrr:.4f}")
    print(f"{'─' * 60}")

    if report.namespace_precision:
        print("\nNamespace precision (fraction of queries returning ≥1 chunk):")
        for ns, prec in sorted(report.namespace_precision.items()):
            bar = "█" * int(prec * 20)
            print(f"  {ns:<20} {prec:.3f}  {bar}")

    if report.by_intent:
        print("\nBreakdown by intent:")
        for intent, metrics in sorted(report.by_intent.items()):
            r5 = metrics.get("recall_at_5", 0)
            mrr_val = metrics.get("mrr", 0)
            print(f"  {intent:<25} Recall@5={r5:.3f}  MRR={mrr_val:.3f}")

    print()

    # ── Failed queries ───────────────────────────────────────────────────────
    failed = [r for r in report.per_query if r.error]
    if failed:
        print(f"Failed queries ({len(failed)}):")
        for r in failed:
            print(f"  [{r.query_id}] {r.error}")
        print()

    # ── Worst performing queries ─────────────────────────────────────────────
    succeeded = [r for r in report.per_query if not r.error]
    worst = sorted(succeeded, key=lambda r: r.recall_at_5)[:5]
    if worst:
        print("5 lowest Recall@5 queries:")
        for r in worst:
            print(f"  [{r.query_id}] Recall@5={r.recall_at_5:.1f}  MRR={r.mrr_score:.3f}  \"{r.query[:60]}...\"")
        print()

    # ── Optional JSON output ─────────────────────────────────────────────────
    if args.output:
        out = args.output
        with open(out, "w") as f:
            json.dump(dataclasses.asdict(report), f, indent=2, default=str)
        print(f"Full report written to: {out}")

    # ── Optional Prometheus push ─────────────────────────────────────────────
    if args.push_metrics:
        _push_to_gateway(report)


def _push_to_gateway(report: object) -> None:
    try:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway  # type: ignore[import-untyped]
        from agents.config import agent_settings

        pushgateway_url = agent_settings.prometheus_pushgateway_url
        if not pushgateway_url:
            print("PROMETHEUS_PUSHGATEWAY_URL not set — skipping push")
            return

        registry = CollectorRegistry()
        for name, value in [
            ("recall_at_5", report.mean_recall_at_5),  # type: ignore[attr-defined]
            ("recall_at_10", report.mean_recall_at_10),  # type: ignore[attr-defined]
            ("mrr", report.mean_mrr),  # type: ignore[attr-defined]
            ("ndcg_at_5", report.mean_ndcg_at_5),  # type: ignore[attr-defined]
            ("ndcg_at_10", report.mean_ndcg_at_10),  # type: ignore[attr-defined]
            ("p95_latency_seconds", report.p95_latency_seconds),  # type: ignore[attr-defined]
        ]:
            g = Gauge(f"career_agents_rag_eval_{name}", name, registry=registry)
            g.set(value)

        push_to_gateway(pushgateway_url, job="rag_eval", registry=registry)
        print(f"Metrics pushed to Prometheus Pushgateway: {pushgateway_url}")
    except Exception as exc:
        print(f"Warning: Pushgateway push failed: {exc}")


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(args))
