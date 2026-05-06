"""search_jobs — MCP tool handler.

Dispatches concurrent search calls to all configured job board sources
(LinkedIn, Indeed, Glassdoor, Swiss Job Portal), merges and deduplicates
results, then returns the combined list in the shape expected by the
market intelligence agent's ``JobBoardFetcher``.

JSON-RPC method: ``search_jobs``
Params: ``SearchJobsParams`` (see models.py)
Result: ``SearchJobsResult``
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseJobBoardClient
from models import (
    JobPosting,
    JobSource,
    SearchJobsParams,
    SearchJobsResult,
)
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    POSTINGS_SKILLS_COUNT,
    POSTINGS_WITH_SALARY,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

_TOOL_NAME = "search_jobs"


async def handle_search_jobs(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseJobBoardClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 60,
) -> dict[str, Any]:
    """Top-level handler for the ``search_jobs`` JSON-RPC method."""
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.search_jobs") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            # ── Input validation ──────────────────────────────────────────
            try:
                search_params = SearchJobsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid search_jobs parameters",
                    data=exc.errors(),
                )

            span.set_attribute("role", search_params.role)
            span.set_attribute("country", search_params.country)

            # ── Rate limiting ─────────────────────────────────────────────
            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for search_jobs")

            # ── Cache lookup ──────────────────────────────────────────────
            cache_key_params = search_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key_params)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                logger.info(
                    "search_jobs.cache_hit",
                    role=search_params.role,
                    country=search_params.country,
                    correlation_id=correlation_id,
                )
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Source selection ──────────────────────────────────────────
            sources_to_query = _select_sources(search_params, clients)
            if not sources_to_query:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    "No job board sources are configured",
                )

            # ── Concurrent fetch ──────────────────────────────────────────
            postings = await _fetch_all_sources(
                search_params, sources_to_query, correlation_id=correlation_id
            )

            # ── Merge, rank, deduplicate ──────────────────────────────────
            merged = _deduplicate(postings)
            ranked = _rank(merged, search_params)
            final = ranked[: search_params.limit]

            # ── Record data quality metrics ───────────────────────────────
            for p in final:
                POSTINGS_SKILLS_COUNT.observe(len(p.required_skills))
                if p.salary_min is not None or p.salary_max is not None:
                    POSTINGS_WITH_SALARY.labels(source=p.source.value).inc()

            # ── Build result ──────────────────────────────────────────────
            from datetime import datetime, timezone

            result = SearchJobsResult(
                postings=[p.model_dump_api() for p in final],
                total_count=len(merged),
                sources_queried=[s.source.value for s in sources_to_query],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            # ── Cache result ──────────────────────────────────────────────
            await cache.set(_TOOL_NAME, cache_key_params, result, ttl=300)

            # ── Audit log ─────────────────────────────────────────────────
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            logger.info(
                "search_jobs.completed",
                role=search_params.role,
                country=search_params.country,
                total_found=len(merged),
                returned=len(final),
                sources=[s.source.value for s in sources_to_query],
                user_id=user_id,
                correlation_id=correlation_id,
            )

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            span.set_attribute("result_count", len(final))
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "search_jobs.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR,
                "Internal error during job search",
            ) from exc


def _select_sources(
    params: SearchJobsParams,
    clients: dict[str, BaseJobBoardClient],
) -> list[BaseJobBoardClient]:
    """Return the clients to query, filtered by params.sources if set."""
    if params.sources:
        return [c for c in clients.values() if c.source in params.sources]
    return list(clients.values())


async def _fetch_all_sources(
    params: SearchJobsParams,
    clients: list[BaseJobBoardClient],
    *,
    correlation_id: str,
) -> list[JobPosting]:
    """Fetch from all sources concurrently. Individual failures return empty lists."""
    tasks = [client.search(params, correlation_id=correlation_id) for client in clients]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    postings: list[JobPosting] = []
    for result in results:
        if isinstance(result, list):
            postings.extend(result)
        elif isinstance(result, Exception):
            logger.warning("search_jobs.source_error", error=str(result))
    return postings


def _deduplicate(postings: list[JobPosting]) -> list[JobPosting]:
    """Remove duplicates keyed on (normalised title, normalised company)."""
    import hashlib

    seen: set[str] = set()
    unique: list[JobPosting] = []
    for p in postings:
        key = hashlib.md5(
            f"{p.title.lower().strip()}:{p.company.lower().strip()}".encode()
        ).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _rank(postings: list[JobPosting], params: SearchJobsParams) -> list[JobPosting]:
    """Score and sort postings by relevance to the search params."""
    query_skills_lower = {s.lower() for s in params.skills}

    def _score(p: JobPosting) -> float:
        score = 0.0
        # Recency bonus
        if p.posted_date:
            from datetime import date
            days_old = (date.today() - p.posted_date).days
            score += max(0.0, 1.0 - days_old / 30)
        # Salary data bonus
        if p.salary_min is not None or p.salary_max is not None:
            score += 0.3
        # Skill match bonus
        if query_skills_lower:
            posting_skills_lower = {s.lower() for s in p.required_skills}
            overlap = len(query_skills_lower & posting_skills_lower)
            score += overlap * 0.2
        # Remote match
        if params.remote is True and p.remote:
            score += 0.2
        return score

    return sorted(postings, key=_score, reverse=True)
