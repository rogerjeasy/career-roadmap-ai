"""search_courses — MCP tool handler.

Dispatches concurrent search calls to all configured course catalogue sources
(Coursera, Udemy, edX, YouTube, O'Reilly), merges and deduplicates results,
then returns the combined list ranked by relevance.

JSON-RPC method: ``search_courses``
Params: ``SearchCoursesParams`` (see models.py)
Result: ``SearchCoursesResult``
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SearchCoursesResult, SkillLevel
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    COURSES_WITH_DURATION,
    COURSES_WITH_RATING,
    FREE_COURSES_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

_TOOL_NAME = "search_courses"


async def handle_search_courses(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseCourseClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    """Top-level handler for the ``search_courses`` JSON-RPC method."""
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.search_courses") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            # ── Input validation ──────────────────────────────────────────
            try:
                search_params = SearchCoursesParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid search_courses parameters",
                    data=exc.errors(),
                )

            span.set_attribute("skill", search_params.skill)
            span.set_attribute("level", search_params.level)

            # ── Rate limiting ─────────────────────────────────────────────
            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(
                    JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for search_courses"
                )

            # ── Cache lookup ──────────────────────────────────────────────
            cache_key_params = search_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key_params)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                logger.info(
                    "search_courses.cache_hit",
                    skill=search_params.skill,
                    level=search_params.level,
                    correlation_id=correlation_id,
                )
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Source selection ──────────────────────────────────────────
            sources_to_query = _select_sources(search_params, clients)
            if not sources_to_query:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    "No course catalogue sources are configured",
                )

            # ── Concurrent fetch ──────────────────────────────────────────
            courses = await _fetch_all_sources(
                search_params, sources_to_query, correlation_id=correlation_id
            )

            # ── Merge, rank, deduplicate ──────────────────────────────────
            merged = _deduplicate(courses)
            ranked = _rank(merged, search_params)
            final = ranked[: search_params.limit]

            # ── Record data quality metrics ───────────────────────────────
            for c in final:
                if c.rating is not None:
                    COURSES_WITH_RATING.labels(source=c.platform.value).inc()
                if c.duration_hours is not None:
                    COURSES_WITH_DURATION.labels(source=c.platform.value).inc()
                if c.free:
                    FREE_COURSES_TOTAL.labels(source=c.platform.value).inc()

            # ── Build result ──────────────────────────────────────────────
            result = SearchCoursesResult(
                courses=[c.model_dump_api() for c in final],
                total_count=len(merged),
                sources_queried=[s.source.value for s in sources_to_query],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            # ── Cache result ──────────────────────────────────────────────
            await cache.set(_TOOL_NAME, cache_key_params, result, ttl=3600)

            # ── Audit log ─────────────────────────────────────────────────
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            logger.info(
                "search_courses.completed",
                skill=search_params.skill,
                level=search_params.level,
                total_found=len(merged),
                returned=len(final),
                sources=[s.source.value for s in sources_to_query],
                user_id=user_id,
                correlation_id=correlation_id,
            )

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="course_catalogue",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            span.set_attribute("result_count", len(final))
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "search_courses.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR,
                "Internal error during course search",
            ) from exc


def _select_sources(
    params: SearchCoursesParams,
    clients: dict[str, BaseCourseClient],
) -> list[BaseCourseClient]:
    if params.sources:
        return [c for c in clients.values() if c.source in params.sources]
    return list(clients.values())


async def _fetch_all_sources(
    params: SearchCoursesParams,
    clients: list[BaseCourseClient],
    *,
    correlation_id: str,
) -> list[Course]:
    tasks = [client.search(params, correlation_id=correlation_id) for client in clients]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    courses: list[Course] = []
    for result in results:
        if isinstance(result, list):
            courses.extend(result)
        elif isinstance(result, Exception):
            logger.warning("search_courses.source_error", error=str(result))
    return courses


def _deduplicate(courses: list[Course]) -> list[Course]:
    """Remove duplicates keyed on normalised title + platform."""
    import hashlib

    seen: set[str] = set()
    unique: list[Course] = []
    for c in courses:
        key = hashlib.md5(
            f"{c.title.lower().strip()}:{c.platform}".encode()
        ).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _rank(courses: list[Course], params: SearchCoursesParams) -> list[Course]:
    """Score and sort courses by relevance to search params."""

    def _score(c: Course) -> float:
        score = 0.0
        # Rating bonus (0–5 scale)
        if c.rating is not None:
            score += c.rating * 0.3
        # Popularity bonus (log-scaled)
        if c.num_ratings:
            import math
            score += min(math.log10(max(c.num_ratings, 1)) * 0.1, 0.5)
        # Level match bonus
        if params.level != SkillLevel.ALL and c.skill_level == params.level:
            score += 0.4
        # Free course bonus when free_only not set but free is nice
        if c.free:
            score += 0.1
        # Has certificate bonus
        if c.certificate:
            score += 0.1
        # Duration data bonus (having duration = more vetted content)
        if c.duration_hours is not None:
            score += 0.05
        return score

    return sorted(courses, key=_score, reverse=True)
