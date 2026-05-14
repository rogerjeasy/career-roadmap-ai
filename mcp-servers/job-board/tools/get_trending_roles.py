"""get_trending_roles — MCP tool handler.

Aggregates trending role data from all job board sources, merges by role
title, and returns a unified ranked list with posting counts, growth signals,
and top required skills.

JSON-RPC method: ``get_trending_roles``
Params: ``GetTrendingRolesParams``
Result: list of TrendingRole dicts
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseJobBoardClient
from models import GetTrendingRolesParams, TrendingRole
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
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

_TOOL_NAME = "get_trending_roles"
_CACHE_TTL = 3600  # trending data changes slowly; cache for 1 hour


async def handle_get_trending_roles(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseJobBoardClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    """Top-level handler for the ``get_trending_roles`` JSON-RPC method."""
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_trending_roles") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            # ── Input validation ──────────────────────────────────────────
            try:
                trend_params = GetTrendingRolesParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid get_trending_roles parameters",
                    data=exc.errors(),
                )

            span.set_attribute("country", trend_params.country)

            # ── Rate limiting ─────────────────────────────────────────────
            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                raise JsonRpcError(
                    JsonRpcErrorCode.RATE_LIMITED,
                    "Rate limit exceeded for get_trending_roles",
                )

            # ── Cache lookup ──────────────────────────────────────────────
            cache_key_params = trend_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key_params)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Concurrent fetch from all sources ─────────────────────────
            tasks = [
                client.get_trending_roles(
                    trend_params.country,
                    trend_params.limit * 2,
                    correlation_id=correlation_id,
                )
                for client in clients.values()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_roles: list[TrendingRole] = []
            for result in results:
                if isinstance(result, list):
                    all_roles.extend(result)

            # ── Merge roles from multiple sources ─────────────────────────
            merged = _merge_trending_roles(all_roles, trend_params.limit)

            # ── Category filter ───────────────────────────────────────────
            if trend_params.category:
                merged = [
                    r for r in merged
                    if trend_params.category.lower() in r.title.lower()
                ]

            from datetime import datetime, timezone

            result_payload = {
                "trending_roles": [r.model_dump() for r in merged[: trend_params.limit]],
                "country": trend_params.country,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "sources": list({s.value for r in merged for s in r.sources}),
            }

            # ── Cache and audit ───────────────────────────────────────────
            await cache.set(_TOOL_NAME, cache_key_params, result_payload, ttl=_CACHE_TTL)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="job_board",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )

            logger.info(
                "get_trending_roles.completed",
                country=trend_params.country,
                roles_count=len(result_payload["trending_roles"]),
                user_id=user_id,
                correlation_id=correlation_id,
                latency_ms=int(latency * 1000),
            )
            return result_payload

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "get_trending_roles.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR,
                "Internal error fetching trending roles",
            ) from exc


_COUNTRY_CURRENCY: dict[str, str] = {
    "CH": "CHF", "DE": "EUR", "FR": "EUR", "AT": "EUR",
    "NL": "EUR", "ES": "EUR", "IT": "EUR", "BE": "EUR",
    "US": "USD", "CA": "CAD", "AU": "AUD", "GB": "GBP",
    "NZ": "NZD", "SG": "SGD", "IN": "INR", "JP": "JPY",
    "BR": "BRL", "MX": "MXN", "ZA": "ZAR", "RU": "RUB",
    "PL": "PLN",
}


def _merge_trending_roles(roles: list[TrendingRole], limit: int) -> list[TrendingRole]:
    """Merge roles with the same normalised title, summing counts and unioning skills."""
    by_title: dict[str, list[TrendingRole]] = defaultdict(list)
    for role in roles:
        key = role.title.lower().strip()
        by_title[key].append(role)

    merged: list[TrendingRole] = []
    for group in by_title.values():
        country = group[0].country
        currency = _COUNTRY_CURRENCY.get(country.upper(), "USD")

        if len(group) == 1:
            single = group[0]
            merged.append(
                TrendingRole(
                    title=single.title,
                    posting_count=single.posting_count,
                    growth_percent=single.growth_percent,
                    top_skills=single.top_skills,
                    median_salary=single.median_salary,
                    currency=currency,
                    country=country,
                    sources=single.sources,
                )
            )
            continue

        total_count = sum(r.posting_count for r in group)
        growths = [r.growth_percent for r in group if r.growth_percent is not None]
        avg_growth: float | None = round(sum(growths) / len(growths), 1) if growths else None

        # Union of skills, ranked by frequency
        skill_count: dict[str, int] = defaultdict(int)
        for r in group:
            for s in r.top_skills:
                skill_count[s.lower()] += 1
        top_skills = [
            s for s, _ in sorted(skill_count.items(), key=lambda x: -x[1])
        ][:8]

        all_sources = list({s for r in group for s in r.sources})
        median_salaries = [r.median_salary for r in group if r.median_salary is not None]
        median_salary = int(sum(median_salaries) / len(median_salaries)) if median_salaries else None

        merged.append(
            TrendingRole(
                title=group[0].title,
                posting_count=total_count,
                growth_percent=avg_growth,
                top_skills=top_skills,
                median_salary=median_salary,
                currency=currency,
                country=country,
                sources=all_sources,
            )
        )

    return sorted(merged, key=lambda r: r.posting_count, reverse=True)
