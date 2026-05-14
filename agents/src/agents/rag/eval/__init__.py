"""RAG evaluation pipeline — offline quality measurement.

Computes Recall@K, MRR, and NDCG@K against a curated ground-truth dataset.
Results are exported as Prometheus Gauge metrics and stored in Redis for
the admin API to surface.

Usage (CLI)::

    cd agents
    poetry run python scripts/eval_rag.py

Usage (Celery)::

    # Via admin API:  POST /api/v1/admin/kb/eval/run
    # Via Beat:       rag.run_eval (weekly, Saturdays 00:00 UTC)
"""
from agents.rag.eval.dataset import EvalQuery, load_eval_dataset
from agents.rag.eval.metrics import ndcg_at_k, mrr, recall_at_k
from agents.rag.eval.runner import EvalReport, EvalRunner, QueryResult

__all__ = [
    "EvalQuery",
    "load_eval_dataset",
    "recall_at_k",
    "mrr",
    "ndcg_at_k",
    "EvalRunner",
    "QueryResult",
    "EvalReport",
]
