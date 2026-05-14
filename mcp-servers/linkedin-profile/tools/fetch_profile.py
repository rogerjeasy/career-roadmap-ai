"""fetch_profile — MCP tool handler."""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.linkedin_profile_client import LinkedInProfileClient
from models import FetchProfileParams
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    PROFILE_FETCH_DURATION,
    PROFILE_FETCH_TOTAL,
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
_TOOL_NAME = "fetch_profile"


async def handle_fetch_profile(
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

    with _tracer.start_as_current_span("tool.fetch_profile") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                fetch_params = FetchProfileParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid fetch_profile parameters",
                    data=exc.errors(),
                )

            span.set_attribute("profile_url", fetch_params.profile_url)

            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                RATE_LIMIT_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for fetch_profile")

            cache_params = {"profile_url": fetch_params.profile_url}
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

            t_fetch = time.monotonic()
            profile = await client.fetch_profile(
                fetch_params.profile_url, correlation_id=correlation_id
            )
            fetch_latency = time.monotonic() - t_fetch
            PROFILE_FETCH_DURATION.observe(fetch_latency)

            if profile is None:
                PROFILE_FETCH_TOTAL.labels(status="not_found").inc()
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Profile not found: {fetch_params.profile_url}",
                )

            PROFILE_FETCH_TOTAL.labels(status="success").inc()

            result = {
                "profile": profile.model_dump_api(),
                "source": "LinkedIn",
            }
            await cache.set(_TOOL_NAME, cache_params, result)

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            emit_tool_call_audit(
                server_id="linkedin_profile", tool=_TOOL_NAME, user_id=user_id,
                outcome="ok", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                extra={"profile_url": fetch_params.profile_url},
            )
            logger.info(
                "fetch_profile.completed",
                profile_id=profile.id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            PROFILE_FETCH_TOTAL.labels(status="error").inc()
            logger.error("fetch_profile.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR, "Internal error during profile fetch"
            ) from exc
