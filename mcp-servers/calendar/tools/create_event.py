"""create_event — MCP tool handler.

Creates a single calendar event on Google Calendar or Outlook.
Suitable for milestone reminders and one-off career planning events.

JSON-RPC method: ``create_event``
Params: ``CreateEventParams`` (see models.py)
Result: ``CreateEventResult``
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from typing import TYPE_CHECKING

from clients.base_client import BaseCalendarClient
from models import CreateEventParams, CreateEventResult

if TYPE_CHECKING:
    from token_store import CalendarTokenStore
from observability import (
    AUDIT_LOG_TOTAL,
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
_TOOL_NAME = "create_event"


async def handle_create_event(
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

    with _tracer.start_as_current_span("tool.create_event") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                p = CreateEventParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid create_event parameters",
                    data=exc.errors(),
                )

            span.set_attribute("provider", p.provider)

            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

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
                event = await client.create_event(
                    access_token=access_token,
                    title=p.title,
                    description=p.description,
                    start=p.start_datetime,
                    end=p.end_datetime,
                    timezone=p.timezone,
                    all_day=p.all_day,
                    location=p.location,
                    reminder_minutes=p.reminder_minutes,
                    calendar_id=p.calendar_id,
                    color_id=p.color_id,
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Failed to create calendar event: {exc}",
                ) from exc

            result = CreateEventResult(
                event=event.model_dump_api(),
                provider=p.provider,
                created_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

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
            span.set_attribute("event_id", event.id)

            logger.info(
                "create_event.completed",
                provider=p.provider,
                event_id=event.id,
                title=p.title,
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
                "create_event.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc
