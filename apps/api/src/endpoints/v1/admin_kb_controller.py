"""Admin endpoints for knowledge-base ingestion.

POST /api/v1/admin/kb/ingest
    Triggers Celery ingestion tasks for one or more KB document types.
    Protected by X-Admin-Api-Key header (compared against ADMIN_API_KEY env var).
    Returns immediately with a list of dispatched Celery task IDs.

All ingestion tasks are idempotent — re-running them overwrites existing
vectors in Pinecone (upsert semantics).
"""
from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.config import get_settings
from src.core.logging import get_logger

router = APIRouter(prefix="/admin/kb", tags=["admin"])
logger = get_logger(__name__)

# Repo root is 5 levels above this file:
# admin_kb_controller.py → v1 → endpoints → src → apps/api → apps → repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]
_KB_DIR = _REPO_ROOT / "agents" / "data" / "knowledge-base"

# ── Document-type enum ────────────────────────────────────────────────────────


class KBDocType(str, Enum):
    career_kb = "career_kb"
    esco = "esco"
    onet = "onet"
    market_reports = "market_reports"
    role_templates = "role_templates"
    swiss_eu_market = "swiss_eu_market"
    global_market = "global_market"


# Absolute paths — resolved at import time so the Celery worker CWD is irrelevant.
_DEFAULT_SOURCE_PATHS: dict[KBDocType, str] = {
    KBDocType.career_kb: str(_KB_DIR / "career_kb_real.json"),
    KBDocType.esco: str(_KB_DIR / "esco_occupations_enriched.csv"),
    KBDocType.onet: str(_KB_DIR / "onet_occupations_enriched.csv"),
    KBDocType.market_reports: str(_KB_DIR / "market_reports_real.json"),
    KBDocType.role_templates: str(_KB_DIR / "role_templates_real.json"),
    KBDocType.swiss_eu_market: str(_KB_DIR / "swiss_eu_market_real.json"),
    KBDocType.global_market: str(_KB_DIR / "global_market_real.json"),
}

# Extra positional args passed to the Celery task for specific doc types.
# ingest_esco accepts source_type as the second positional arg ("esco" by default).
_TASK_EXTRA_ARGS: dict[KBDocType, list[str]] = {
    KBDocType.onet: ["onet"],
}

# Additional real-data paths not mapped to a single doc_type.
_EXTRA_ESCO_PATHS: list[str] = [
    str(_KB_DIR / "esco_skills.csv"),
]

# ── Request / response schemas ─────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Body for POST /admin/kb/ingest."""

    doc_type: KBDocType | None = Field(
        default=None,
        description=(
            "Shorthand for ingesting a single document type. "
            "Mutually exclusive with doc_types — if both are provided, "
            "doc_type is ignored."
        ),
    )
    doc_types: list[KBDocType] = Field(
        default_factory=list,
        description=(
            "Which document types to ingest. "
            "Empty list (and no doc_type) → ingest all types."
        ),
    )
    source_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional map of doc_type → absolute source path. "
            "Overrides the default path for the specified types."
        ),
    )


class DispatchedTask(BaseModel):
    doc_type: KBDocType
    task_id: str
    source_path: str


class IngestResponse(BaseModel):
    dispatched: list[DispatchedTask]
    message: str


class SeedRequest(BaseModel):
    """Body for POST /admin/kb/seed."""

    output_dir: str = Field(
        default="agents/data/knowledge-base",
        description="Directory to write generated files. Must be writable by the Celery worker.",
    )
    fetch_esco: bool = Field(
        default=False,
        description="Fetch real ESCO taxonomy data from the public REST API (requires internet).",
    )
    esco_limit: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Max ESCO occupations to fetch when fetch_esco=True.",
    )
    ingest_after: bool = Field(
        default=True,
        description="Dispatch ingestion tasks immediately after seed file generation.",
    )


class SeedResponse(BaseModel):
    task_id: str
    message: str


class UploadSourcesResponse(BaseModel):
    task_id: str
    files_queued: int
    message: str


class FitBM25Response(BaseModel):
    task_id: str
    source_count: int
    message: str


class EvalRunResponse(BaseModel):
    task_id: str
    queries_count: int
    message: str


class EvalResultsResponse(BaseModel):
    found: bool
    timestamp: str | None = None
    mean_recall_at_5: float | None = None
    mean_recall_at_10: float | None = None
    mean_mrr: float | None = None
    mean_ndcg_at_5: float | None = None
    mean_ndcg_at_10: float | None = None
    p95_latency_seconds: float | None = None
    namespace_precision: dict | None = None
    by_intent: dict | None = None
    total_queries: int | None = None
    failed_queries: int | None = None
    message: str


# ── Auth helper ───────────────────────────────────────────────────────────────


def _verify_admin_key(x_admin_api_key: str | None) -> None:
    """Raise 403 if the header is missing or doesn't match ADMIN_API_KEY."""
    _admin_key = get_settings().admin_api_key
    expected = _admin_key.get_secret_value() if _admin_key else ""
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key not configured on this server.",
        )
    if x_admin_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Api-Key header.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger knowledge-base ingestion",
    description=(
        "Dispatches background Celery tasks to ingest one or more document types "
        "into the Pinecone vector store. Tasks are idempotent — existing vectors "
        "are overwritten (upsert). Requires X-Admin-Api-Key header."
    ),
)
async def trigger_ingestion(
    body: IngestRequest,
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> IngestResponse:
    _verify_admin_key(x_admin_api_key)

    # Lazy import so this controller stays importable even when the agents
    # package Celery tasks haven't been fully configured (e.g., in unit tests).
    from agents.rag.tasks.ingestion_tasks import (  # noqa: PLC0415
        ingest_career_kb,
        ingest_esco,
        ingest_global_market,
        ingest_market_reports,
        ingest_role_templates,
        ingest_swiss_eu_market,
    )

    _task_map = {
        KBDocType.career_kb: ingest_career_kb,
        KBDocType.esco: ingest_esco,
        KBDocType.onet: ingest_esco,
        KBDocType.market_reports: ingest_market_reports,
        KBDocType.role_templates: ingest_role_templates,
        KBDocType.swiss_eu_market: ingest_swiss_eu_market,
        KBDocType.global_market: ingest_global_market,
    }

    if body.doc_types:
        types_to_run = body.doc_types
    elif body.doc_type:
        types_to_run = [body.doc_type]
    else:
        types_to_run = list(KBDocType)
    dispatched: list[DispatchedTask] = []

    for doc_type in types_to_run:
        source_path = body.source_overrides.get(doc_type.value) or _DEFAULT_SOURCE_PATHS[doc_type]
        task_fn = _task_map[doc_type]
        extra_args = _TASK_EXTRA_ARGS.get(doc_type, [])

        try:
            async_result = task_fn.delay(source_path, *extra_args)
            dispatched.append(
                DispatchedTask(
                    doc_type=doc_type,
                    task_id=async_result.id,
                    source_path=source_path,
                )
            )
            logger.info(
                "admin.kb.ingest_dispatched",
                doc_type=doc_type.value,
                task_id=async_result.id,
                source_path=source_path,
            )
        except Exception as exc:
            logger.error(
                "admin.kb.ingest_dispatch_failed",
                doc_type=doc_type.value,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to dispatch ingestion task for '{doc_type.value}': {exc}",
            ) from exc

    # After a full-corpus ingest, schedule BM25 encoder refitting.
    # A 10-minute countdown lets all ingestion tasks finish first.
    is_full_ingest = not body.doc_types or set(body.doc_types) == set(KBDocType)
    if is_full_ingest:
        try:
            from agents.config import agent_settings as _agent_settings  # noqa: PLC0415
            from agents.rag.tasks.ingestion_tasks import fit_bm25_encoder  # noqa: PLC0415
            if _agent_settings.hybrid_search_enabled:
                bm25_paths = [
                    p for p in _DEFAULT_SOURCE_PATHS.values() if Path(p).exists()
                ]
                fit_bm25_encoder.apply_async(
                    args=[bm25_paths],
                    countdown=600,
                    queue="agents.ingestion",
                )
                logger.info(
                    "admin.kb.bm25_refit_scheduled",
                    countdown_seconds=600,
                    source_count=len(bm25_paths),
                )
        except Exception as exc:
            logger.warning("admin.kb.bm25_refit_schedule_failed", error=str(exc))

    return IngestResponse(
        dispatched=dispatched,
        message=f"Dispatched {len(dispatched)} ingestion task(s).",
    )


@router.post(
    "/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate and ingest comprehensive KB seed data",
    description=(
        "Dispatches a background Celery task that generates comprehensive seed data files "
        "(role templates, career KB articles, market reports, Swiss/EU market data, ESCO taxonomy) "
        "and optionally ingests them into Pinecone immediately. "
        "Requires X-Admin-Api-Key header."
    ),
)
async def trigger_seed(
    body: SeedRequest,
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> SeedResponse:
    _verify_admin_key(x_admin_api_key)

    from agents.rag.tasks.ingestion_tasks import seed_knowledge_base  # noqa: PLC0415

    try:
        async_result = seed_knowledge_base.delay(
            output_dir=body.output_dir,
            fetch_esco=body.fetch_esco,
            esco_limit=body.esco_limit,
            ingest_after=body.ingest_after,
        )
        logger.info(
            "admin.kb.seed_dispatched",
            task_id=async_result.id,
            output_dir=body.output_dir,
            fetch_esco=body.fetch_esco,
            ingest_after=body.ingest_after,
        )
        return SeedResponse(
            task_id=async_result.id,
            message=(
                "Seed task dispatched. "
                f"Poll GET /admin/kb/ingest/status/{async_result.id} for progress."
            ),
        )
    except Exception as exc:
        logger.error("admin.kb.seed_dispatch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch seed task: {exc}",
        ) from exc


@router.get(
    "/ingest/status/{task_id}",
    summary="Poll ingestion task status",
)
async def get_ingest_status(
    task_id: str,
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Return the current state of a KB ingestion Celery task."""
    _verify_admin_key(x_admin_api_key)

    from agents.bus.celery_app import celery_app  # noqa: PLC0415
    from celery.result import AsyncResult  # noqa: PLC0415

    result: AsyncResult = celery_app.AsyncResult(task_id)
    state = result.state

    if state == "SUCCESS":
        return {"task_id": task_id, "state": state, "result": result.result}
    if state == "FAILURE":
        return {"task_id": task_id, "state": state, "error": str(result.result)}
    return {"task_id": task_id, "state": state}


@router.post(
    "/fit-bm25",
    response_model=FitBM25Response,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Fit BM25 encoder on the current KB corpus",
    description=(
        "Dispatches a background Celery task that reads the source files, fits a "
        "domain-specific BM25 encoder on the chunk texts, and uploads the fitted "
        "params to Cloudinary. Workers automatically download these params on next "
        "construction (no BM25_ENCODER_PATH restart needed). "
        "Only meaningful when HYBRID_SEARCH_ENABLED=true. "
        "Requires X-Admin-Api-Key header."
    ),
)
async def trigger_bm25_fit(
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> FitBM25Response:
    _verify_admin_key(x_admin_api_key)

    from agents.rag.tasks.ingestion_tasks import fit_bm25_encoder  # noqa: PLC0415

    source_paths = [p for p in _DEFAULT_SOURCE_PATHS.values() if Path(p).exists()]
    source_paths += [p for p in _EXTRA_ESCO_PATHS if Path(p).exists()]

    if not source_paths:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No source files found in the default KB directory.",
        )

    try:
        async_result = fit_bm25_encoder.apply_async(
            args=[source_paths],
            queue="agents.ingestion",
        )
        logger.info(
            "admin.kb.bm25_fit_dispatched",
            task_id=async_result.id,
            source_count=len(source_paths),
        )
        return FitBM25Response(
            task_id=async_result.id,
            source_count=len(source_paths),
            message=(
                f"BM25 fit task dispatched across {len(source_paths)} source file(s). "
                f"Poll GET /admin/kb/ingest/status/{async_result.id} for progress. "
                "Workers will automatically load the fitted params from Cloudinary "
                "on their next BM25SparseEncoder construction."
            ),
        )
    except Exception as exc:
        logger.error("admin.kb.bm25_fit_dispatch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch BM25 fit task: {exc}",
        ) from exc


@router.post(
    "/upload-sources",
    response_model=UploadSourcesResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload raw source files to Cloudinary",
    description=(
        "Dispatches a background Celery task that uploads the raw KB source files "
        "(JSON / CSV) to Cloudinary for archiving and replay. Use this endpoint to "
        "backfill documents that were ingested before Cloudinary archiving was enabled. "
        "Requires X-Admin-Api-Key header."
    ),
)
async def trigger_source_upload(
    body: IngestRequest,
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> UploadSourcesResponse:
    _verify_admin_key(x_admin_api_key)

    from agents.rag.tasks.ingestion_tasks import upload_source_documents  # noqa: PLC0415

    if body.doc_types:
        types_to_run = body.doc_types
    elif body.doc_type:
        types_to_run = [body.doc_type]
    else:
        types_to_run = list(KBDocType)
    source_entries: list[dict[str, str]] = []

    for doc_type in types_to_run:
        path = body.source_overrides.get(doc_type.value) or _DEFAULT_SOURCE_PATHS.get(doc_type)
        if path:
            source_entries.append({
                "path": path,
                "doc_type": doc_type.value,
                "public_id": f"kb/{doc_type.value}/{Path(path).name}",
            })

    # Also include extra taxonomy files (esco_skills.csv etc.) on full runs.
    if not body.doc_types:
        for extra_path in _EXTRA_ESCO_PATHS:
            source_entries.append({
                "path": extra_path,
                "doc_type": "esco",
                "public_id": f"kb/esco/{Path(extra_path).name}",
            })

    try:
        async_result = upload_source_documents.delay(source_entries)
        logger.info(
            "admin.kb.upload_sources_dispatched",
            task_id=async_result.id,
            files=len(source_entries),
        )
        return UploadSourcesResponse(
            task_id=async_result.id,
            files_queued=len(source_entries),
            message=(
                f"Upload task dispatched for {len(source_entries)} file(s). "
                f"Poll GET /admin/kb/ingest/status/{async_result.id} for progress."
            ),
        )
    except Exception as exc:
        logger.error("admin.kb.upload_sources_dispatch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch upload task: {exc}",
        ) from exc


@router.post(
    "/eval/run",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run offline RAG eval pipeline",
    description=(
        "Dispatches a Celery task that evaluates retrieval quality against the "
        "curated ground-truth dataset (agents/data/eval/rag_eval.jsonl). "
        "Computes Recall@5, Recall@10, MRR, NDCG@5, NDCG@10 and p95 latency. "
        "Results are pushed to Prometheus Gauges and stored in Redis for "
        "GET /admin/kb/eval/results. "
        "Requires X-Admin-Api-Key header."
    ),
)
async def trigger_eval_run(
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> EvalRunResponse:
    _verify_admin_key(x_admin_api_key)

    from agents.rag.eval.dataset import load_eval_dataset  # noqa: PLC0415
    from agents.rag.tasks.ingestion_tasks import run_eval_pipeline  # noqa: PLC0415

    try:
        queries = load_eval_dataset()
        async_result = run_eval_pipeline.apply_async(queue="agents.ingestion")
        logger.info(
            "admin.kb.eval_dispatched",
            task_id=async_result.id,
            queries_count=len(queries),
        )
        return EvalRunResponse(
            task_id=async_result.id,
            queries_count=len(queries),
            message=(
                f"Eval task dispatched for {len(queries)} queries. "
                f"Poll GET /admin/kb/ingest/status/{async_result.id} for progress. "
                "Results available at GET /admin/kb/eval/results once complete."
            ),
        )
    except Exception as exc:
        logger.error("admin.kb.eval_dispatch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch eval task: {exc}",
        ) from exc


@router.get(
    "/eval/results",
    response_model=EvalResultsResponse,
    summary="Retrieve latest RAG eval results",
    description=(
        "Returns the most recent RAG eval report stored in Redis. "
        "Run POST /admin/kb/eval/run first to populate results. "
        "Requires X-Admin-Api-Key header."
    ),
)
async def get_eval_results(
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> EvalResultsResponse:
    _verify_admin_key(x_admin_api_key)

    try:
        import json  # noqa: PLC0415

        import redis as _redis  # noqa: PLC0415

        from src.config import get_settings  # noqa: PLC0415
        _settings = get_settings()
        r = _redis.from_url(str(_settings.redis_url))
        raw = await asyncio.to_thread(r.get, "rag:eval:latest")
        r.close()

        if raw is None:
            return EvalResultsResponse(
                found=False,
                message="No eval results found. Run POST /admin/kb/eval/run first.",
            )

        data = json.loads(raw)
        return EvalResultsResponse(
            found=True,
            timestamp=data.get("timestamp"),
            mean_recall_at_5=data.get("mean_recall_at_5"),
            mean_recall_at_10=data.get("mean_recall_at_10"),
            mean_mrr=data.get("mean_mrr"),
            mean_ndcg_at_5=data.get("mean_ndcg_at_5"),
            mean_ndcg_at_10=data.get("mean_ndcg_at_10"),
            p95_latency_seconds=data.get("p95_latency_seconds"),
            namespace_precision=data.get("namespace_precision"),
            by_intent=data.get("by_intent"),
            total_queries=data.get("total_queries"),
            failed_queries=data.get("failed_queries"),
            message="Latest eval results retrieved successfully.",
        )
    except Exception as exc:
        logger.error("admin.kb.eval_results_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve eval results: {exc}",
        ) from exc
