"""suggest_connections — MCP tool handler."""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.linkedin_profile_client import LinkedInProfileClient
from models import SuggestConnectionsParams
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    CONNECTION_SUGGEST_RESULTS,
    CONNECTION_SUGGEST_TOTAL,
    RATE_LIMIT_HIT_TOTAL,
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
_TOOL_NAME = "suggest_connections"


async def handle_suggest_connections(
    params: dict[str, Any],
    request: Request,
    client: LinkedInProfileClient | None,
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 20,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.suggest_connections") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                sugg_params = SuggestConnectionsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid suggest_connections parameters",
                    data=exc.errors(),
                )

            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                RATE_LIMIT_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for suggest_connections")

            cache_params = sugg_params.model_dump(exclude={"access_token"})
            cached = await cache.get(_TOOL_NAME, cache_params)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                latency = time.monotonic() - t0
                emit_tool_call_audit(
                    server_id="linkedin_profile", tool=_TOOL_NAME, user_id=user_id,
                    outcome="cache_hit", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                )
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            if client is None:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    "LinkedIn Profile API is not configured. Set LINKEDIN_API_KEY.",
                )

            suggestions = await client.search_people(
                keywords=sugg_params.skills,
                location=sugg_params.location,
                limit=sugg_params.limit,
                correlation_id=correlation_id,
            )

            CONNECTION_SUGGEST_TOTAL.labels(status="success").inc()
            CONNECTION_SUGGEST_RESULTS.observe(len(suggestions))

            from datetime import UTC, datetime
            result = {
                "suggestions": [s.model_dump() for s in suggestions],
                "total_count": len(suggestions),
                "target_role": sugg_params.target_role,
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            await cache.set(_TOOL_NAME, cache_params, result, ttl=1800)

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            emit_tool_call_audit(
                server_id="linkedin_profile", tool=_TOOL_NAME, user_id=user_id,
                outcome="ok", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                extra={"suggestion_count": len(suggestions)},
            )
            span.set_attribute("result_count", len(suggestions))
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            CONNECTION_SUGGEST_TOTAL.labels(status="error").inc()
            logger.error("suggest_connections.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR, "Internal error during connection suggestions"
            ) from exc
