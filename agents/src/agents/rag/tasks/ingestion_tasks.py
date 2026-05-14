"""Celery tasks for background ingestion of knowledge-base documents.

Triggered by:
  - Admin API endpoint: POST /admin/kb/ingest
  - Celery Beat schedule (nightly backfill)
  - One-off CLI invocation for bulk backfills

Each task is idempotent — re-ingesting the same document_id overwrites
existing vectors in Pinecone (upsert semantics). Retries up to 3 times
on transient failures with exponential back-off via Celery's built-in
retry mechanism.

When ``hybrid_search_enabled=True``, all ingestion tasks load a
``BM25SparseEncoder`` (from ``bm25_encoder_path`` if set, else MS-MARCO
default) and attach sparse vectors to every chunk.

After ingestion, each task uploads the raw source file to Cloudinary
(when Cloudinary credentials are configured) so the original documents
are archived and replayable without re-fetching from the seed scripts.

The ``rag.fit_bm25_encoder`` task re-fits the encoder on fresh corpus text and
uploads the new params to Cloudinary. Run it after a bulk re-ingest to keep
BM25 weights aligned with the live corpus.

The ``rag.upload_source_documents`` task uploads a list of source files to
Cloudinary. Use it to backfill documents that were ingested before Cloudinary
archiving was enabled.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from opentelemetry.trace import StatusCode

from agents.bus.celery_app import celery_app
from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.ingestion.chunker import SemanticChunker
from agents.rag.ingestion.embedder import OpenAIEmbedder
from agents.rag.ingestion.indexer import PineconeIndexer
from agents.rag.ingestion.loaders.career_kb_loader import CareerKBLoader
from agents.rag.ingestion.loaders.esco_loader import ESCOLoader
from agents.rag.ingestion.loaders.global_market_loader import GlobalMarketLoader
from agents.rag.ingestion.loaders.market_reports_loader import MarketReportsLoader
from agents.rag.ingestion.loaders.role_templates_loader import RoleTemplatesLoader
from agents.rag.ingestion.loaders.swiss_eu_market_loader import SwissEUMarketLoader
from agents.rag.observability import (
    RAG_BM25_FIT_DURATION,
    RAG_BM25_FIT_TOTAL,
    RAG_CHUNKS_CREATED_TOTAL,
    RAG_DOCS_INGESTED_TOTAL,
    RAG_INGESTION_TASK_DURATION,
    RAG_INGESTION_TASK_TOTAL,
    RAG_SOURCE_UPLOAD_TOTAL,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.tasks.ingestion")


@celery_app.task(name="rag.ingest_career_kb", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_career_kb(self: Any, source_path: str) -> dict[str, int]:
    """Ingest career KB articles from a JSON file."""
    return asyncio.get_event_loop().run_until_complete(
        _run_ingestion(
            CareerKBLoader(source=Path(source_path)),
            "career_kb",
            source_path=source_path,
            task_id=self.request.id,
        )
    )


@celery_app.task(name="rag.ingest_esco", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_esco(
    self: Any, source_path: str, source_type: str = "esco"
) -> dict[str, int]:
    """Ingest ESCO / O*NET taxonomy from a CSV file."""
    return asyncio.get_event_loop().run_until_complete(
        _run_ingestion(
            ESCOLoader(source=Path(source_path), source_type=source_type),
            "esco_onet",
            source_path=source_path,
            task_id=self.request.id,
        )
    )


@celery_app.task(name="rag.ingest_market_reports", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_market_reports(self: Any, source_path: str) -> dict[str, int]:
    """Ingest job market reports from a JSON file."""
    return asyncio.get_event_loop().run_until_complete(
        _run_ingestion(
            MarketReportsLoader(source=Path(source_path)),
            "market_report",
            source_path=source_path,
            task_id=self.request.id,
        )
    )


@celery_app.task(name="rag.ingest_role_templates", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_role_templates(self: Any, source_path: str) -> dict[str, int]:
    """Ingest role requirement templates from a JSON file."""
    return asyncio.get_event_loop().run_until_complete(
        _run_ingestion(
            RoleTemplatesLoader(source=Path(source_path)),
            "role_template",
            source_path=source_path,
            task_id=self.request.id,
        )
    )


@celery_app.task(name="rag.ingest_swiss_eu_market", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_swiss_eu_market(self: Any, source_path: str) -> dict[str, int]:
    """Ingest Swiss/EU market documents from a JSON file."""
    return asyncio.get_event_loop().run_until_complete(
        _run_ingestion(
            SwissEUMarketLoader(source=Path(source_path)),
            "swiss_eu_market",
            source_path=source_path,
            task_id=self.request.id,
        )
    )


@celery_app.task(name="rag.ingest_global_market", bind=True, max_retries=3)  # type: ignore[misc]
def ingest_global_market(self: Any, source_path: str) -> dict[str, int]:
    """Ingest global market documents (Asia, LATAM, Africa, MENA, Oceania) from a JSON file.

    Covers all job families and industries — not just technology.
    Documents land in the ``global-market`` Pinecone namespace and are routed
    to users outside the US/EU/CH region by the ContextAssembler.
    """
    try:
        return asyncio.get_event_loop().run_until_complete(
            _run_ingestion(
                GlobalMarketLoader(source=Path(source_path)),
                "global_market",
                source_path=source_path,
                task_id=self.request.id,
            )
        )
    except Exception as exc:
        # Retry on transient upstream errors (Pinecone 502/503, OpenAI 429/5xx).
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@celery_app.task(name="rag.seed_knowledge_base", bind=True, max_retries=1)  # type: ignore[misc]
def seed_knowledge_base(
    self: Any,
    output_dir: str = "agents/data/knowledge-base",
    fetch_esco: bool = False,
    esco_limit: int = 500,
    ingest_after: bool = True,
) -> dict[str, Any]:
    """Generate comprehensive seed data files and optionally trigger ingestion.

    Parameters
    ----------
    output_dir:
        Directory where generated JSON/CSV files are written.
    fetch_esco:
        If True, also fetch real ESCO taxonomy data from the public REST API.
    esco_limit:
        Maximum number of ESCO occupations to fetch from the API.
    ingest_after:
        If True, dispatch all ingestion tasks immediately after generation.
        When ``hybrid_search_enabled=True``, also dispatches ``fit_bm25_encoder``
        after the ingestion tasks (with a 5-minute countdown to let them complete).
    """
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    # Ensure the agents package root is importable regardless of working directory.
    pkg_root = str(Path(__file__).resolve().parents[4])
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    from agents.scripts.seed_knowledge_base import (  # noqa: PLC0415
        generate_career_kb,
        generate_esco_taxonomy,
        generate_market_reports,
        generate_role_templates,
        generate_swiss_eu_market,
        fetch_esco_occupations,
        write_json,
        write_csv,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    templates = generate_role_templates()
    write_json(out / "role_templates_full.json", templates, "role_templates", verbose=False)

    articles = generate_career_kb()
    write_json(out / "career_kb_full.json", articles, "career_kb", verbose=False)

    reports = generate_market_reports()
    write_json(out / "market_reports_full.json", reports, "market_reports", verbose=False)

    swiss_eu = generate_swiss_eu_market()
    write_json(out / "swiss_eu_market_full.json", swiss_eu, "swiss_eu_market", verbose=False)

    esco_rows = generate_esco_taxonomy()
    write_csv(
        out / "esco_taxonomy.csv",
        esco_rows,
        ["conceptUri", "preferredLabel", "altLabels", "description"],
        "esco_taxonomy",
        verbose=False,
    )

    live_esco_count = 0
    if fetch_esco:
        live_rows = fetch_esco_occupations(limit=esco_limit, verbose=False)
        if live_rows:
            write_csv(
                out / "esco_taxonomy_live.csv",
                live_rows,
                ["conceptUri", "preferredLabel", "altLabels", "description"],
                "esco_live",
                verbose=False,
            )
            live_esco_count = len(live_rows)

    summary = {
        "role_templates": len(templates),
        "career_kb": len(articles),
        "market_reports": len(reports),
        "swiss_eu_market": len(swiss_eu),
        "esco_synthetic": len(esco_rows),
        "esco_live": live_esco_count,
        "output_dir": str(out.resolve()),
    }

    logger.info("rag.seed_knowledge_base.generated", **summary)

    if ingest_after:
        ingest_career_kb.delay(str(out / "career_kb_full.json"))
        ingest_role_templates.delay(str(out / "role_templates_full.json"))
        ingest_market_reports.delay(str(out / "market_reports_full.json"))
        ingest_swiss_eu_market.delay(str(out / "swiss_eu_market_full.json"))
        ingest_esco.delay(str(out / "esco_taxonomy.csv"), source_type="esco")
        if live_esco_count:
            ingest_esco.delay(str(out / "esco_taxonomy_live.csv"), source_type="esco")

        # Re-fit BM25 encoder after corpus is refreshed.
        # Countdown of 300s gives ingestion tasks time to complete first.
        if agent_settings.hybrid_search_enabled:
            bm25_paths = [
                str(out / "career_kb_full.json"),
                str(out / "role_templates_full.json"),
                str(out / "market_reports_full.json"),
                str(out / "swiss_eu_market_full.json"),
                str(out / "esco_taxonomy.csv"),
            ]
            fit_bm25_encoder.apply_async(
                args=[bm25_paths],
                countdown=300,
                queue="agents.ingestion",
            )

        logger.info("rag.seed_knowledge_base.ingestion_dispatched")

    return summary


@celery_app.task(name="rag.fit_bm25_encoder", bind=True, max_retries=3)  # type: ignore[misc]
def fit_bm25_encoder(self: Any, source_paths: list[str]) -> dict[str, Any]:
    """Fit BM25 encoder on corpus text from the given source files and upload to Cloudinary.

    ``source_paths`` is a list of JSON or CSV file paths — the same files used
    by the ingest tasks. Chunk texts are extracted and used to fit the encoder.
    After fitting, the params JSON is uploaded to Cloudinary so all workers
    pick it up on next startup.

    Run this task after a full corpus re-ingest to keep BM25 weights current.
    """
    return asyncio.get_event_loop().run_until_complete(
        _fit_and_upload_bm25(source_paths)
    )


@celery_app.task(name="rag.upload_source_documents", bind=True, max_retries=3)  # type: ignore[misc]
def upload_source_documents(
    self: Any, source_entries: list[dict[str, str]]
) -> dict[str, Any]:
    """Upload raw source files to Cloudinary for archiving and replay.

    ``source_entries`` is a list of dicts, each with keys:
      - ``path``      — absolute or relative path to the local file
      - ``doc_type``  — label used for the Cloudinary tag and metric label
      - ``public_id`` — (optional) Cloudinary public_id; defaults to kb/{doc_type}/{filename}

    Use this task to backfill documents that were ingested before Cloudinary
    archiving was enabled, or to re-upload after credentials change.
    """
    return asyncio.get_event_loop().run_until_complete(
        _upload_sources(source_entries)
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _run_ingestion(
    loader: Any,
    doc_type_label: str,
    *,
    source_path: str | None = None,
    task_id: str | None = None,
) -> dict[str, int]:
    """Load -> chunk -> embed (dense + optional sparse) -> upsert.

    After upserting, uploads the raw source file to Cloudinary if the
    Cloudinary credentials are configured.  The upload is non-blocking on
    error — a Cloudinary failure never aborts ingestion.

    Returns {"docs": N, "chunks": M}.
    """
    import time  # noqa: PLC0415

    t0 = time.monotonic()
    with _tracer.start_as_current_span("rag.ingestion.run") as span:
        span.set_attribute("doc_type", doc_type_label)
        span.set_attribute("hybrid", agent_settings.hybrid_search_enabled)
        if task_id:
            span.set_attribute("task_id", task_id)

        try:
            chunker = SemanticChunker()
            embedder = OpenAIEmbedder()
            indexer = PineconeIndexer()

            sparse_encoder = None
            if agent_settings.hybrid_search_enabled:
                from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder  # noqa: PLC0415
                sparse_encoder = BM25SparseEncoder(params_path=agent_settings.bm25_encoder_path)

            docs_count = 0
            chunks_count = 0

            async for doc in loader.load():
                docs_count += 1
                chunks = chunker.chunk(doc)
                chunks_count += len(chunks)

                embedded = await embedder.embed_chunks(chunks, sparse_encoder=sparse_encoder)
                await indexer.upsert(embedded)

                RAG_DOCS_INGESTED_TOTAL.labels(doc_type=doc_type_label).inc()
                RAG_CHUNKS_CREATED_TOTAL.labels(doc_type=doc_type_label).inc(len(chunks))

            elapsed = time.monotonic() - t0
            RAG_INGESTION_TASK_DURATION.labels(doc_type=doc_type_label).observe(elapsed)
            RAG_INGESTION_TASK_TOTAL.labels(doc_type=doc_type_label, status="success").inc()

            span.set_attribute("docs_ingested", docs_count)
            span.set_attribute("chunks_created", chunks_count)
            span.set_attribute("elapsed_seconds", round(elapsed, 2))
            span.set_status(StatusCode.OK)

            logger.info(
                "rag.ingestion.complete",
                doc_type=doc_type_label,
                docs=docs_count,
                chunks=chunks_count,
                elapsed_seconds=round(elapsed, 2),
                hybrid=agent_settings.hybrid_search_enabled,
                task_id=task_id or "n/a",
            )

            # Archive the raw source file to Cloudinary after successful ingestion.
            if source_path:
                await _upload_source_to_cloudinary(source_path, doc_type_label)

            return {"docs": docs_count, "chunks": chunks_count}

        except Exception as exc:
            elapsed = time.monotonic() - t0
            RAG_INGESTION_TASK_DURATION.labels(doc_type=doc_type_label).observe(elapsed)
            RAG_INGESTION_TASK_TOTAL.labels(doc_type=doc_type_label, status="error").inc()
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            logger.error(
                "rag.ingestion.failed",
                doc_type=doc_type_label,
                elapsed_seconds=round(elapsed, 2),
                error=str(exc),
                task_id=task_id or "n/a",
            )
            raise


async def _upload_source_to_cloudinary(path: str, doc_type: str) -> None:
    """Upload a single source file to Cloudinary. Non-blocking on any error."""
    from agents.rag.storage.cloudinary_client import get_cloudinary_client  # noqa: PLC0415

    client = get_cloudinary_client()
    if client is None:
        return  # Cloudinary not configured — skip silently

    p = Path(path)
    if not p.exists():
        logger.warning("rag.source_upload.file_not_found", path=path)
        return

    public_id = f"kb/{doc_type}/{p.name}"
    try:
        await client.upload(
            p,
            public_id=public_id,
            doc_type=doc_type,
            tags=[doc_type, "knowledge-base"],
        )
        RAG_SOURCE_UPLOAD_TOTAL.labels(doc_type=doc_type, status="success").inc()
        logger.info("rag.source_upload.done", path=path, public_id=public_id)
    except Exception as exc:
        RAG_SOURCE_UPLOAD_TOTAL.labels(doc_type=doc_type, status="error").inc()
        logger.warning("rag.source_upload.failed", path=path, error=str(exc))


async def _upload_sources(source_entries: list[dict[str, str]]) -> dict[str, Any]:
    """Upload a batch of source files to Cloudinary."""
    from agents.rag.storage.cloudinary_client import get_cloudinary_client  # noqa: PLC0415

    client = get_cloudinary_client()
    if client is None:
        logger.warning("rag.upload_sources.cloudinary_not_configured")
        return {"uploaded": 0, "failed": 0, "skipped": len(source_entries)}

    uploaded = 0
    failed = 0

    for entry in source_entries:
        path_str = entry.get("path", "")
        doc_type = entry.get("doc_type", "document")
        p = Path(path_str)
        public_id = entry.get("public_id") or f"kb/{doc_type}/{p.name}"

        if not p.exists():
            logger.warning("rag.upload_sources.file_not_found", path=path_str)
            failed += 1
            continue

        try:
            await client.upload(
                p,
                public_id=public_id,
                doc_type=doc_type,
                tags=[doc_type, "knowledge-base"],
            )
            RAG_SOURCE_UPLOAD_TOTAL.labels(doc_type=doc_type, status="success").inc()
            uploaded += 1
            logger.info(
                "rag.upload_sources.uploaded",
                path=path_str,
                public_id=public_id,
            )
        except Exception as exc:
            RAG_SOURCE_UPLOAD_TOTAL.labels(doc_type=doc_type, status="error").inc()
            logger.error(
                "rag.upload_sources.failed",
                path=path_str,
                error=str(exc),
            )
            failed += 1

    logger.info(
        "rag.upload_sources.complete",
        uploaded=uploaded,
        failed=failed,
        total=len(source_entries),
    )
    return {"uploaded": uploaded, "failed": failed, "total": len(source_entries)}


async def _fit_and_upload_bm25(source_paths: list[str]) -> dict[str, Any]:
    """Collect all chunk texts, fit BM25 encoder, upload to Cloudinary."""
    import time  # noqa: PLC0415

    from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder  # noqa: PLC0415

    t0 = time.monotonic()
    with _tracer.start_as_current_span("rag.bm25.fit") as span:
        span.set_attribute("source_count", len(source_paths))
        try:
            chunker = SemanticChunker()
            corpus: list[str] = []

            loaders: list[Any] = []
            for path in source_paths:
                p = Path(path)
                if p.suffix == ".csv":
                    loaders.append(ESCOLoader(source=p))
                elif "market_report" in p.name:
                    loaders.append(MarketReportsLoader(source=p))
                elif "role_template" in p.name:
                    loaders.append(RoleTemplatesLoader(source=p))
                elif "swiss" in p.name:
                    loaders.append(SwissEUMarketLoader(source=p))
                elif "global_market" in p.name:
                    loaders.append(GlobalMarketLoader(source=p))
                else:
                    loaders.append(CareerKBLoader(source=p))

            for loader in loaders:
                async for doc in loader.load():
                    chunks = chunker.chunk(doc)
                    corpus.extend(c.content for c in chunks)

            encoder = BM25SparseEncoder()
            encoder.fit(corpus)
            public_id = await encoder.save_to_cloudinary()

            elapsed = time.monotonic() - t0
            RAG_BM25_FIT_DURATION.observe(elapsed)
            RAG_BM25_FIT_TOTAL.labels(status="success").inc()

            span.set_attribute("corpus_size", len(corpus))
            span.set_attribute("elapsed_seconds", round(elapsed, 2))
            span.set_status(StatusCode.OK)

            logger.info(
                "rag.bm25.fit_task_complete",
                corpus_size=len(corpus),
                elapsed_seconds=round(elapsed, 2),
                public_id=public_id,
            )
            return {"corpus_chunks": len(corpus), "cloudinary_public_id": public_id}

        except Exception as exc:
            elapsed = time.monotonic() - t0
            RAG_BM25_FIT_DURATION.observe(elapsed)
            RAG_BM25_FIT_TOTAL.labels(status="error").inc()
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            logger.error(
                "rag.bm25.fit_task_failed",
                elapsed_seconds=round(elapsed, 2),
                error=str(exc),
            )
            raise


# ── Eval pipeline task ────────────────────────────────────────────────────────


@celery_app.task(  # type: ignore[misc]
    name="rag.run_eval",
    bind=True,
    max_retries=1,
    queue="agents.ingestion",
)
def run_eval_pipeline(
    self: Any,
    dataset_path: str | None = None,
) -> dict[str, Any]:
    """Run the RAG eval pipeline and push quality metrics to Prometheus + Redis.

    Executes all queries in ``rag_eval.jsonl`` against the live Pinecone index
    using the production retriever config (hybrid BM25, domain-fitted encoder).
    Results are:
      - Pushed as Prometheus Gauge values (picked up by the metrics scraper).
      - Stored as JSON in Redis under ``rag:eval:latest`` for the admin API.
      - Returned as the Celery task result for status polling.
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_eval_async(dataset_path)
    )


async def _run_eval_async(dataset_path: str | None) -> dict[str, Any]:
    import dataclasses
    import json
    import time

    from agents.rag.eval.dataset import load_eval_dataset
    from agents.rag.eval.runner import EvalRunner, build_retriever
    from agents.rag.observability import (
        RAG_EVAL_DURATION,
        RAG_EVAL_MRR,
        RAG_EVAL_NAMESPACE_PRECISION,
        RAG_EVAL_NDCG_AT_K,
        RAG_EVAL_P95_LATENCY,
        RAG_EVAL_RECALL_AT_K,
        RAG_EVAL_RUN_TOTAL,
    )

    t0 = time.monotonic()
    try:
        queries = load_eval_dataset(dataset_path)
        retriever = build_retriever()
        runner = EvalRunner(retriever)
        report = await runner.run(queries, dataset_path=dataset_path or "rag_eval.jsonl")

        # ── Push Prometheus Gauge metrics ─────────────────────────────────────
        RAG_EVAL_RECALL_AT_K.labels(k="5").set(report.mean_recall_at_5)
        RAG_EVAL_RECALL_AT_K.labels(k="10").set(report.mean_recall_at_10)
        RAG_EVAL_MRR.set(report.mean_mrr)
        RAG_EVAL_NDCG_AT_K.labels(k="5").set(report.mean_ndcg_at_5)
        RAG_EVAL_NDCG_AT_K.labels(k="10").set(report.mean_ndcg_at_10)
        RAG_EVAL_P95_LATENCY.set(report.p95_latency_seconds)
        for ns, precision in report.namespace_precision.items():
            RAG_EVAL_NAMESPACE_PRECISION.labels(namespace=ns).set(precision)

        RAG_EVAL_DURATION.observe(time.monotonic() - t0)
        RAG_EVAL_RUN_TOTAL.labels(status="success").inc()

        # ── Store in Redis for admin GET /eval/results ────────────────────────
        result_dict = dataclasses.asdict(report)
        try:
            import redis  # type: ignore[import-untyped]
            r = redis.from_url(str(agent_settings.redis_url))
            r.setex("rag:eval:latest", 7 * 24 * 3600, json.dumps(result_dict, default=str))
            r.close()
        except Exception as redis_exc:
            logger.warning("rag.eval.redis_store_failed", error=str(redis_exc))

        logger.info("rag.eval.task_complete", summary=report.summary())
        return result_dict

    except Exception as exc:
        RAG_EVAL_DURATION.observe(time.monotonic() - t0)
        RAG_EVAL_RUN_TOTAL.labels(status="error").inc()
        logger.error("rag.eval.task_failed", error=str(exc))
        raise
