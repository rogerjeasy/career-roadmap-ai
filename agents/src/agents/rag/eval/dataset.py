"""Ground-truth eval dataset for the RAG pipeline.

Each entry in ``rag_eval.jsonl`` defines a query, the namespaces that should
contain relevant results, and domain keywords that must appear in a retrieved
chunk for it to count as relevant.  This label-free approach avoids hard-coding
chunk IDs (which change on re-ingestion) while still measuring meaningful
retrieval quality.

Relevance rule (applied per chunk):
  1. The chunk's namespace is in ``expected_namespaces``, AND
  2. The chunk's content contains at least ``min_keyword_hits`` of the
     ``expected_keywords`` (case-insensitive substring match).

When ``expected_keywords`` is empty, any chunk from the expected namespaces
is considered relevant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_EVAL_PATH = (
    Path(__file__).resolve().parents[5] / "data" / "eval" / "rag_eval.jsonl"
)


@dataclass
class EvalQuery:
    id: str
    query: str
    intent: str
    # ── Real (chunk-based) queries ─────────────────────────────────────────
    # Set by generate_eval_dataset.py; ground truth is the exact Pinecone chunk.
    chunk_id: str = ""       # Pinecone vector ID of the source chunk
    namespace: str = ""      # namespace the source chunk lives in
    doc_id: str = ""         # doc_id metadata field of the source chunk
    # ── Synthetic (keyword-based) queries — legacy fallback ───────────────
    expected_namespaces: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    min_keyword_hits: int = 1
    description: str = ""


def load_eval_dataset(path: str | Path | None = None) -> list[EvalQuery]:
    """Load eval queries from a JSONL file.

    Defaults to ``agents/data/eval/rag_eval.jsonl`` when ``path`` is None.
    Each line must be a valid JSON object matching the ``EvalQuery`` fields.
    Blank lines are silently skipped.
    """
    p = Path(path) if path else _DEFAULT_EVAL_PATH
    queries: list[EvalQuery] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            queries.append(
                EvalQuery(
                    id=d["id"],
                    query=d["query"],
                    intent=d["intent"],
                    chunk_id=d.get("chunk_id", ""),
                    namespace=d.get("namespace", ""),
                    doc_id=d.get("doc_id", ""),
                    expected_namespaces=d.get("expected_namespaces", []),
                    expected_keywords=d.get("expected_keywords", []),
                    min_keyword_hits=d.get("min_keyword_hits", 1),
                    description=d.get("description", ""),
                )
            )
    return queries
