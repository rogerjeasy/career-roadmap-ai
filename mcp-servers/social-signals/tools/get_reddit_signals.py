"""get_reddit_signals — MCP tool handler.

Fetches top Reddit posts from tech-relevant subreddits for the
requested stacks using the public Reddit JSON API (no auth required).

JSON-RPC method: ``get_reddit_signals``
Params: ``GetRedditSignalsParams`` (see models.py)
Result: ``SocialSignalsResult``
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseSocialClient
from models import GetRedditSignalsParams, SocialSignalsResult
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

_TOOL_NAME = "get_reddit_signals"


async def handle_get_reddit_signals(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseSocialClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 60,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_reddit_signals") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                p = GetRedditSignalsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid get_reddit_signals parameters",
                    data=exc.errors(),
                )

            span.set_attribute("stacks", ",".join(p.stacks))

            allowed = await rate_limiter.check(user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60)
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            cache_key = p.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            reddit_client = clients.get("reddit")
            if not reddit_client:
                raise JsonRpcError(JsonRpcErrorCode.UPSTREAM_ERROR, "Reddit client not configured")

            signals = await reddit_client.search(
                p.stacks,
                p.limit,
                correlation_id=correlation_id,
                subreddits=p.subreddits or None,
                time_filter=p.time_filter,
                sort=p.sort,
            )

            result = SocialSignalsResult(
                signals=[s.model_dump_api() for s in signals],
                total_count=len(signals),
                stacks_queried=p.stacks,
                source="Reddit",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result)

            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="social_signals",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            span.set_attribute("result_count", len(signals))

            logger.info(
                "get_reddit_signals.completed",
                stacks=p.stacks,
                count=len(signals),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "get_reddit_signals.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc
