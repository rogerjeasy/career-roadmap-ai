"""get_trending_repos — MCP tool handler.

Searches GitHub for repositories that have been recently active and are
gaining momentum (stars, pushes) in a given programming language.

JSON-RPC method: ``get_trending_repos``
Params: ``GetTrendingReposParams``
Result: ``GetTrendingReposResult``
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.github_client import GitHubClient
from models import GetTrendingReposParams, GetTrendingReposResult
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    GITHUB_FETCH_DURATION,
    GITHUB_FETCH_TOTAL,
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

_TOOL_NAME = "get_trending_repos"


async def handle_get_trending_repos(
    params: dict[str, Any],
    request: Request,
    github: GitHubClient,
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_trending_repos") as span:
        span.set_attribute("user_id", user_id)

        t0 = time.monotonic()
        try:
            try:
                search_params = GetTrendingReposParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(JsonRpcErrorCode.INVALID_PARAMS, "Invalid parameters", data=exc.errors())

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

            fetch_t0 = time.monotonic()
            try:
                repos = await github.get_trending_repos(search_params)
                GITHUB_FETCH_TOTAL.labels(endpoint="search/repositories", status="ok").inc()
            except Exception as exc:
                GITHUB_FETCH_TOTAL.labels(endpoint="search/repositories", status="error").inc()
                raise JsonRpcError(JsonRpcErrorCode.UPSTREAM_ERROR, f"GitHub API error: {exc}") from exc
            finally:
                GITHUB_FETCH_DURATION.labels(endpoint="search/repositories").observe(time.monotonic() - fetch_t0)

            result = GetTrendingReposResult(
                repos=[r.model_dump_api() for r in repos],
                total_count=len(repos),
                language=search_params.language,
                since_days=search_params.since_days,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result, ttl=1800)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="github_trends",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )

            logger.info(
                "get_trending_repos.completed",
                language=search_params.language,
                since_days=search_params.since_days,
                count=len(repos),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("get_trending_repos.error", error=str(exc), exc_info=True)
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc
