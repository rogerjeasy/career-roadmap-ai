"""list_upcoming — MCP tool handler.

Lists upcoming calendar events from Google Calendar or Outlook within a
configurable time window. Results are cached per (user, provider, time range)
for 5 minutes to reduce upstream API quota consumption.

JSON-RPC method: ``list_upcoming``
Params: ``ListUpcomingParams`` (see models.py)
Result: ``ListUpcomingResult``
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseCalendarClient
from models import ListUpcomingParams, ListUpcomingResult
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
_TOOL_NAME = "list_upcoming"


async def handle_list_upcoming(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseCalendarClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
    token_store: Any = None,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.list_upcoming") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                p = ListUpcomingParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid list_upcoming parameters",
                    data=exc.errors(),
                )

            span.set_attribute("provider", p.provider)

            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            # Exclude access_token from cache key to avoid token leakage into Redis keys
            cache_key = {
                **p.model_dump(exclude={"access_token"}),
                "user_id": user_id,
            }
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # Resolve access token — use request param first, fall back to token store
            access_token = p.access_token
            if not access_token and token_store is not None:
                access_token = await token_store.get_access_token(user_id, p.provider.value)
            if not access_token:
                raise JsonRpcError(
                    JsonRpcErrorCode.UNAUTHORIZED,
                    "No access token provided. Supply 'access_token' in the request "
                    "or call store_oauth_token first.",
                )

            client = clients.get(p.provider)
            if not client:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Calendar provider '{p.provider}' not configured",
                )

            try:
                events = await client.list_upcoming(
                    access_token=access_token,
                    max_results=p.max_results,
                    time_min=p.time_min,
                    time_max=p.time_max,
                    timezone=p.timezone,
                    calendar_id=p.calendar_id,
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Failed to list calendar events: {exc}",
                ) from exc

            result = ListUpcomingResult(
                events=[e.model_dump_api() for e in events],
                total_count=len(events),
                provider=p.provider,
                time_min=p.time_min,
                time_max=p.time_max,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result)

            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="calendar",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            span.set_attribute("result_count", len(events))

            logger.info(
                "list_upcoming.completed",
                provider=p.provider,
                count=len(events),
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
                "list_upcoming.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc
