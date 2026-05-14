"""get_salary_range — MCP tool handler.

Fetches salary benchmark data for a given role, country, and experience level
from Glassdoor (RapidAPI) and levels.fyi. Falls back to a curated Swiss/EU
AI-roles dataset when external sources are unavailable.

JSON-RPC method: ``get_salary_range``
Params: ``GetSalaryRangeParams``
Result: ``GetSalaryRangeResult``
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseSalaryClient
from models import (
    ExperienceLevel,
    GetSalaryRangeParams,
    GetSalaryRangeResult,
    SalaryDataPoint,
    SalaryRange,
    SalarySource,
)
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    SALARY_FETCH_DURATION,
    SALARY_FETCH_TOTAL,
    SALARY_SAMPLE_COUNT,
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

_TOOL_NAME = "get_salary_range"

# ── Curated Swiss/EU AI-ML salary dataset (CHF, gross annual) ─────────────────
# Source: Glassdoor CH reports 2024–2025, Robert Half Technology Salary Guide 2025,
# SwissICT salary survey 2024. Values in CHF unless noted.
_CURATED: list[dict[str, Any]] = [
    {"role": "Machine Learning Engineer", "country": "CH", "level": "entry", "p25": 90000, "median": 105000, "p75": 120000, "currency": "CHF"},
    {"role": "Machine Learning Engineer", "country": "CH", "level": "mid",   "p25": 120000, "median": 140000, "p75": 160000, "currency": "CHF"},
    {"role": "Machine Learning Engineer", "country": "CH", "level": "senior","p25": 150000, "median": 175000, "p75": 200000, "currency": "CHF"},
    {"role": "Machine Learning Engineer", "country": "CH", "level": "lead",  "p25": 175000, "median": 210000, "p75": 250000, "currency": "CHF"},
    {"role": "AI Engineer",               "country": "CH", "level": "entry", "p25": 88000,  "median": 102000, "p75": 118000, "currency": "CHF"},
    {"role": "AI Engineer",               "country": "CH", "level": "mid",   "p25": 118000, "median": 138000, "p75": 158000, "currency": "CHF"},
    {"role": "AI Engineer",               "country": "CH", "level": "senior","p25": 148000, "median": 172000, "p75": 195000, "currency": "CHF"},
    {"role": "Data Scientist",            "country": "CH", "level": "entry", "p25": 80000,  "median": 95000,  "p75": 112000, "currency": "CHF"},
    {"role": "Data Scientist",            "country": "CH", "level": "mid",   "p25": 110000, "median": 130000, "p75": 150000, "currency": "CHF"},
    {"role": "Data Scientist",            "country": "CH", "level": "senior","p25": 140000, "median": 165000, "p75": 185000, "currency": "CHF"},
    {"role": "Software Engineer",         "country": "CH", "level": "entry", "p25": 75000,  "median": 90000,  "p75": 105000, "currency": "CHF"},
    {"role": "Software Engineer",         "country": "CH", "level": "mid",   "p25": 100000, "median": 120000, "p75": 140000, "currency": "CHF"},
    {"role": "Software Engineer",         "country": "CH", "level": "senior","p25": 130000, "median": 155000, "p75": 175000, "currency": "CHF"},
    {"role": "Machine Learning Engineer", "country": "DE", "level": "entry", "p25": 55000,  "median": 65000,  "p75": 78000,  "currency": "EUR"},
    {"role": "Machine Learning Engineer", "country": "DE", "level": "mid",   "p25": 72000,  "median": 85000,  "p75": 100000, "currency": "EUR"},
    {"role": "Machine Learning Engineer", "country": "DE", "level": "senior","p25": 95000,  "median": 115000, "p75": 135000, "currency": "EUR"},
    {"role": "Machine Learning Engineer", "country": "US", "level": "entry", "p25": 130000, "median": 155000, "p75": 185000, "currency": "USD"},
    {"role": "Machine Learning Engineer", "country": "US", "level": "mid",   "p25": 170000, "median": 210000, "p75": 260000, "currency": "USD"},
    {"role": "Machine Learning Engineer", "country": "US", "level": "senior","p25": 220000, "median": 280000, "p75": 360000, "currency": "USD"},
]


async def handle_get_salary_range(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseSalaryClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    """Top-level handler for the ``get_salary_range`` JSON-RPC method."""
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_salary_range") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                search_params = GetSalaryRangeParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid get_salary_range parameters",
                    data=exc.errors(),
                )

            span.set_attribute("role", search_params.role)
            span.set_attribute("country", search_params.country)

            allowed = await rate_limiter.check(user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60)
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            cache_key = search_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Fetch from live sources ───────────────────────────────────
            all_points: list[SalaryDataPoint] = []
            for name, client in clients.items():
                fetch_t0 = time.monotonic()
                try:
                    points = await client.fetch(search_params)
                    all_points.extend(points)
                    SALARY_FETCH_TOTAL.labels(source=name, status="ok").inc()
                    SALARY_FETCH_DURATION.labels(source=name).observe(time.monotonic() - fetch_t0)
                except Exception as exc:
                    SALARY_FETCH_TOTAL.labels(source=name, status="error").inc()
                    logger.warning("get_salary_range.source_failed", source=name, error=str(exc))

            # ── Curated fallback ──────────────────────────────────────────
            curated = _get_curated_range(search_params)
            live_ranges = _aggregate(all_points, search_params)

            ranges = live_ranges if live_ranges else ([curated] if curated else [])

            if not ranges:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"No salary data found for '{search_params.role}' in {search_params.country}",
                )

            SALARY_SAMPLE_COUNT.observe(len(all_points))

            result = GetSalaryRangeResult(
                ranges=[r.model_dump_api() for r in ranges],
                role=search_params.role,
                country=search_params.country,
                total_sources=len({p.source for p in all_points}) + (1 if curated and not live_ranges else 0),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result, ttl=3600)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="salary_benchmark",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )

            logger.info(
                "get_salary_range.completed",
                role=search_params.role,
                country=search_params.country,
                level=search_params.experience_level,
                data_points=len(all_points),
                ranges=len(ranges),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("get_salary_range.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc


def _aggregate(
    points: list[SalaryDataPoint],
    params: GetSalaryRangeParams,
) -> list[SalaryRange]:
    """Group salary points by experience level and compute percentiles."""
    if not points:
        return []

    by_level: dict[ExperienceLevel, list[int]] = {}
    sources_by_level: dict[ExperienceLevel, set[SalarySource]] = {}

    for p in points:
        if p.country != params.country:
            continue
        by_level.setdefault(p.experience_level, []).append(p.base_salary)
        sources_by_level.setdefault(p.experience_level, set()).add(p.source)

    ranges: list[SalaryRange] = []
    now = datetime.now(timezone.utc).isoformat()

    for level, salaries in by_level.items():
        if not salaries:
            continue
        salaries_sorted = sorted(salaries)
        n = len(salaries_sorted)

        def pct(p: float) -> int:
            idx = int(p / 100 * n)
            return salaries_sorted[min(idx, n - 1)]

        ranges.append(
            SalaryRange(
                role=params.role,
                country=params.country,
                currency=params.currency,
                experience_level=level,
                p10=pct(10) if n >= 5 else None,
                p25=pct(25) if n >= 4 else None,
                median=int(statistics.median(salaries_sorted)),
                p75=pct(75) if n >= 4 else None,
                p90=pct(90) if n >= 5 else None,
                sample_count=n,
                sources=list(sources_by_level.get(level, set())),
                fetched_at=now,
            )
        )

    return ranges


def _get_curated_range(params: GetSalaryRangeParams) -> SalaryRange | None:
    """Return the closest curated salary range from the embedded dataset."""
    role_lower = params.role.lower()
    level_str = params.experience_level.value

    # Find best role match
    for entry in _CURATED:
        if (
            entry["country"] == params.country
            and entry["level"] == level_str
            and _role_matches(entry["role"], role_lower)
        ):
            currency = entry.get("currency", params.currency)
            return SalaryRange(
                role=entry["role"],
                country=params.country,
                currency=currency,
                experience_level=params.experience_level,
                p25=entry.get("p25"),
                median=entry["median"],
                p75=entry.get("p75"),
                sample_count=0,  # indicates curated data
                sources=[SalarySource.CURATED],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

    # Fallback: any matching country+level regardless of role
    for entry in _CURATED:
        if entry["country"] == params.country and entry["level"] == level_str:
            currency = entry.get("currency", params.currency)
            return SalaryRange(
                role=entry["role"],
                country=params.country,
                currency=currency,
                experience_level=params.experience_level,
                p25=entry.get("p25"),
                median=entry["median"],
                p75=entry.get("p75"),
                sample_count=0,
                sources=[SalarySource.CURATED],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

    return None


def _role_matches(curated_role: str, query_lower: str) -> bool:
    words = curated_role.lower().split()
    return any(w in query_lower for w in words if len(w) > 3)
