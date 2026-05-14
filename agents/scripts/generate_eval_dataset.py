#!/usr/bin/env python
"""Generate a real ground-truth RAG eval dataset from live Pinecone chunks.

For each namespace, samples up to --per-namespace chunks from the live index,
then calls Claude Haiku to generate 2-3 career-domain questions that each chunk
directly answers.  Writes (question, chunk_id, namespace, doc_id) tuples to
agents/data/eval/rag_eval_real.jsonl.

Retrieval is correct when the source chunk_id appears in the top-K results.
This is the strongest possible eval — ground truth is rooted in real content.

Usage
-----
    cd agents
    poetry run python scripts/generate_eval_dataset.py
    poetry run python scripts/generate_eval_dataset.py --per-namespace 100
    poetry run python scripts/generate_eval_dataset.py --questions-per-chunk 3 --dry-run

Requirements
------------
- PINECONE_API_KEY, PINECONE_INDEX_NAME in environment (loaded from .env)
- ANTHROPIC_API_KEY in environment
- Pinecone serverless index with content stored in chunk metadata
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

_AGENTS_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _AGENTS_SRC not in sys.path:
    sys.path.insert(0, _AGENTS_SRC)

# ── Namespace → intent mapping ────────────────────────────────────────────────
# Maps each namespace to the orchestrator intent whose retrieval set includes it.
# Ensures the source namespace is always searched during eval.
_NS_INTENT: dict[str, str] = {
    "career-kb":       "roadmap_generation",
    "taxonomy":        "gap_analysis",
    "role-templates":  "gap_analysis",
    "market-reports":  "market_intelligence",
    "swiss-eu-market": "market_intelligence",
}

_ALL_NAMESPACES = list(_NS_INTENT.keys())

_SYSTEM_PROMPT = """\
You are building a retrieval evaluation dataset for an AI career coaching system.

Given a knowledge-base chunk, generate exactly {n} concise questions that:
1. A career professional or job-seeker would naturally ask
2. This specific chunk directly and completely answers
3. Use domain-specific terminology from the chunk (job titles, tool names, \
skills, locations, companies, certifications)
4. Are self-contained — answerable without seeing other chunks

Output ONLY a valid JSON array of {n} question strings.
No explanation, no preamble, no trailing text.
Example output: ["Question one?", "Question two?"]"""

_USER_PROMPT = """\
Namespace: {namespace}
Chunk content:
{content}"""


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate real eval queries from live Pinecone chunks"
    )
    p.add_argument(
        "--per-namespace", type=int, default=50,
        help="Chunks to sample per namespace (default: 50)",
    )
    p.add_argument(
        "--questions-per-chunk", type=int, default=2, choices=[2, 3],
        help="Questions to generate per chunk (default: 2)",
    )
    p.add_argument(
        "--namespaces", nargs="+", default=_ALL_NAMESPACES,
        help=f"Namespaces to sample from (default: all {len(_ALL_NAMESPACES)})",
    )
    p.add_argument(
        "--output", default=None,
        help="Output path (default: agents/data/eval/rag_eval_real.jsonl)",
    )
    p.add_argument(
        "--concurrency", type=int, default=2,
        help="Max concurrent Claude Haiku calls (default: 2, keeps under 50 RPM)",
    )
    p.add_argument(
        "--request-delay", type=float, default=1.5,
        help="Seconds to sleep after each successful LLM call (default: 1.5)",
    )
    p.add_argument(
        "--max-retries", type=int, default=4,
        help="Max retries on rate-limit errors with exponential backoff (default: 4)",
    )
    p.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible chunk sampling (default: 42)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Sample chunks and print a preview without calling Claude or writing output",
    )
    return p.parse_args()


async def _list_and_sample_ids(
    index: object,
    namespace: str,
    n: int,
    seed: int,
) -> list[str]:
    """Sample up to n chunk IDs from a Pinecone namespace via list() pagination.

    Collects up to 5×n IDs (capped at 2000) then draws a random sample,
    giving better diversity than taking the first page only.
    """
    target_pool = min(n * 5, 2000)
    ids: list[str] = []

    def _collect() -> None:
        # index.list() is a generator that yields lists of IDs (serverless only)
        for id_batch in index.list(namespace=namespace, limit=100):  # type: ignore[attr-defined]
            ids.extend(id_batch)
            if len(ids) >= target_pool:
                break

    await asyncio.to_thread(_collect)

    if not ids:
        print(f"  [{namespace}] No IDs returned from list() - skipping")
        return []

    rng = random.Random(seed)
    sampled = rng.sample(ids, min(n, len(ids)))
    print(f"  [{namespace}] Pool: {len(ids)} IDs -> sampled {len(sampled)}")
    return sampled


async def _fetch_chunks(
    index: object,
    ids: list[str],
    namespace: str,
) -> list[dict]:
    """Fetch chunk metadata for the given IDs via Pinecone fetch()."""
    def _fetch() -> object:
        return index.fetch(ids=ids, namespace=namespace)  # type: ignore[attr-defined]

    response = await asyncio.to_thread(_fetch)
    chunks = []
    for chunk_id, vector in response.vectors.items():
        meta = vector.metadata or {}
        content = str(meta.get("content", "")).strip()
        if not content:
            continue  # skip chunks with no stored content
        chunks.append({
            "chunk_id": chunk_id,
            "namespace": namespace,
            "content": content,
            "doc_id": str(meta.get("doc_id", "")),
            "doc_type": str(meta.get("doc_type", "")),
            "title": str(meta.get("title", "")),
        })
    return chunks


async def _generate_questions(
    llm: object,
    chunk: dict,
    n_questions: int,
    semaphore: asyncio.Semaphore,
    *,
    request_delay: float = 1.5,
    max_retries: int = 4,
) -> list[str]:
    """Call Claude Haiku to generate n_questions for a single chunk.

    Retries up to max_retries times on 429 rate-limit errors with exponential
    backoff.  Returns an empty list on persistent failure so the caller skips
    the chunk.
    """
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    system = _SYSTEM_PROMPT.format(n=n_questions)
    user = _USER_PROMPT.format(
        namespace=chunk["namespace"],
        content=chunk["content"][:2000],  # cap at ~500 tokens
    )
    cid = chunk["chunk_id"][:16]

    async with semaphore:
        for attempt in range(max_retries + 1):
            try:
                response = await llm.ainvoke(  # type: ignore[attr-defined]
                    [SystemMessage(content=system), HumanMessage(content=user)]
                )
                raw = str(response.content).strip()

                # Throttle after a successful call to stay under 50 RPM
                await asyncio.sleep(request_delay)

                # Robustly extract JSON array from the response
                start = raw.find("[")
                end = raw.rfind("]") + 1
                if start == -1 or end == 0:
                    if attempt < max_retries:
                        print(f"    [warn] No JSON array for chunk {cid} — retrying ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    print(f"    [warn] No JSON array for chunk {cid} after {max_retries} retries — skipping")
                    return []
                questions: list[str] = json.loads(raw[start:end])
                if not isinstance(questions, list):
                    return []
                return [q.strip() for q in questions if isinstance(q, str) and q.strip()]

            except Exception as exc:
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "rate_limit" in err_str
                if is_rate_limit and attempt < max_retries:
                    wait = 60 if attempt == 0 else 2 ** (attempt + 5)
                    print(f"    [rate-limit] chunk {cid} — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                print(f"    [warn] LLM call failed for chunk {cid}: {exc}")
                return []
        return []


async def _main(args: argparse.Namespace) -> None:
    from agents.config import agent_settings

    # ── Connect to Pinecone ───────────────────────────────────────────────────
    try:
        from pinecone import Pinecone  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: pinecone package not installed. Run: poetry add pinecone")
        sys.exit(1)

    api_key = (
        agent_settings.pinecone_api_key.get_secret_value()
        if agent_settings.pinecone_api_key else None
    )
    if not api_key:
        print("ERROR: PINECONE_API_KEY not set")
        sys.exit(1)

    index_name = agent_settings.pinecone_index_name
    if not index_name:
        print("ERROR: PINECONE_INDEX_NAME not set")
        sys.exit(1)

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)
    print(f"Connected to Pinecone index: {index_name}")

    # ── Connect to Claude Haiku (question generation) ─────────────────────────
    anthropic_key = (
        agent_settings.anthropic_api_key.get_secret_value()
        if agent_settings.anthropic_api_key else None
    )
    if not anthropic_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    llm = None
    if not args.dry_run:
        from langchain_anthropic import ChatAnthropic  # noqa: PLC0415
        llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=anthropic_key,
            max_tokens=512,
            temperature=0.3,
        )

    semaphore = asyncio.Semaphore(args.concurrency)

    # ── Output path ───────────────────────────────────────────────────────────
    default_output = (
        Path(__file__).resolve().parents[1]
        / "data" / "eval" / "rag_eval_real.jsonl"
    )
    output_path = Path(args.output) if args.output else default_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Process each namespace ────────────────────────────────────────────────
    all_entries: list[dict] = []
    t_start = time.monotonic()

    for namespace in args.namespaces:
        if namespace not in _NS_INTENT:
            print(f"[skip] Unknown namespace: {namespace}")
            continue

        intent = _NS_INTENT[namespace]
        print(f"\n[{namespace}] -> intent: {intent}")

        ids = await _list_and_sample_ids(index, namespace, args.per_namespace, args.seed)
        if not ids:
            continue

        chunks = await _fetch_chunks(index, ids, namespace)
        print(f"  [{namespace}] Fetched {len(chunks)} chunks with content")

        if args.dry_run:
            print(f"  [{namespace}] DRY RUN - skipping question generation")
            for chunk in chunks[:3]:
                preview = chunk["content"][:80].encode("ascii", "replace").decode("ascii")
                print(f"    chunk_id={chunk['chunk_id'][:32]}  content={preview}...")
            continue

        # Generate questions concurrently across all chunks in this namespace
        tasks = [
            _generate_questions(
                llm, chunk, args.questions_per_chunk, semaphore,
                request_delay=args.request_delay,
                max_retries=args.max_retries,
            )
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks)

        ns_entries = 0
        for chunk, questions in zip(chunks, results):
            for q_idx, question in enumerate(questions):
                # Use last 16 chars of chunk_id (contains the unique hash suffix)
                entry_id = f"real_{namespace.replace('-', '_')}_{chunk['chunk_id'][-16:]}_q{q_idx + 1}"
                all_entries.append({
                    "id": entry_id,
                    "query": question,
                    "intent": intent,
                    "chunk_id": chunk["chunk_id"],
                    "namespace": namespace,
                    "doc_id": chunk["doc_id"],
                    "description": (
                        f"Generated from {namespace} chunk "
                        f"{chunk['chunk_id'][:16]} "
                        f"(doc: {chunk['doc_id'] or 'unknown'})"
                    ),
                })
                ns_entries += 1

        print(f"  [{namespace}] Generated {ns_entries} questions from {len(chunks)} chunks")

    if args.dry_run:
        print(f"\nDRY RUN complete - no file written")
        return

    # ── Write output ──────────────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    elapsed = time.monotonic() - t_start
    print(f"\n{'-' * 60}")
    print(f"Generated {len(all_entries)} eval queries in {elapsed:.1f}s")
    print(f"Written to: {output_path}")
    print(f"{'-' * 60}")
    print("\nBreakdown by namespace:")
    ns_counts: dict[str, int] = {}
    for e in all_entries:
        ns_counts[e["namespace"]] = ns_counts.get(e["namespace"], 0) + 1
    for ns, count in sorted(ns_counts.items()):
        print(f"  {ns:<22} {count:>4} questions")
    print(f"\nRun the eval with:")
    print(f"  poetry run python scripts/eval_rag.py --dataset {output_path}")


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(args))
