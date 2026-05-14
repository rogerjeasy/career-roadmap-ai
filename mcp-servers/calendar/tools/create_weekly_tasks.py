"""create_weekly_tasks — MCP tool handler.

Converts a week's career roadmap tasks into calendar events on Google Calendar
or Outlook. Each task is placed on the correct day of the week at the specified
time, with automatic color-coding by task type and configurable reminders.

JSON-RPC method: ``create_weekly_tasks``
Params: ``CreateWeeklyTasksParams`` (see models.py)
Result: ``CreateWeeklyTasksResult``
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseCalendarClient
from models import (
    GOOGLE_COLOR_BY_TASK_TYPE,
    CalendarProvider,
    CreateWeeklyTasksParams,
    CreateWeeklyTasksResult,
    WeeklyTask,
)
from observability import (
    AUDIT_LOG_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    WEEKLY_TASKS_CREATED,
    WEEKLY_TASKS_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()
_TOOL_NAME = "create_weekly_tasks"


def _build_event_kwargs(
    task: WeeklyTask,
    week_start_date: date,
    tz: ZoneInfo,
    default_reminder_minutes: list[int],
    calendar_id: str,
    provider: CalendarProvider,
) -> dict[str, Any]:
    """Compute create_event kwargs for a single task."""
    event_date = week_start_date + timedelta(days=task.day_of_week)
    h, m = (int(x) for x in task.start_time.split(":"))
    start_dt = datetime(event_date.year, event_date.month, event_date.day, h, m, 0, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=task.duration_minutes)

    reminders = task.reminder_minutes if task.reminder_minutes else default_reminder_minutes

    color_id = ""
    if provider == CalendarProvider.GOOGLE:
        color_id = GOOGLE_COLOR_BY_TASK_TYPE.get(task.task_type, "")

    return {
        "title": task.title,
        "description": task.description,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "timezone": str(tz),
        "all_day": False,
        "location": "",
        "reminder_minutes": reminders,
        "calendar_id": calendar_id,
        "color_id": color_id,
        "_day_of_week": task.day_of_week,  # popped in BaseCalendarClient.create_events_batch
    }


async def handle_create_weekly_tasks(
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

    with _tracer.start_as_current_span("tool.create_weekly_tasks") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        provider_name = str(params.get("provider", "unknown"))
        try:
            try:
                p = CreateWeeklyTasksParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid create_weekly_tasks parameters",
                    data=exc.errors(),
                )

            provider_name = p.provider.value
            span.set_attribute("provider", provider_name)
            span.set_attribute("task_count", len(p.tasks))

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
                week_start_date = date.fromisoformat(p.week_start)
            except ValueError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    f"Invalid week_start date: {p.week_start}",
                ) from exc

            try:
                tz = ZoneInfo(p.timezone)
            except (ZoneInfoNotFoundError, KeyError):
                logger.warning("create_weekly_tasks.unknown_tz", timezone=p.timezone)
                tz = ZoneInfo("UTC")

            events_kwargs = [
                _build_event_kwargs(
                    task=task,
                    week_start_date=week_start_date,
                    tz=tz,
                    default_reminder_minutes=p.default_reminder_minutes,
                    calendar_id=p.calendar_id,
                    provider=p.provider,
                )
                for task in p.tasks
            ]

            created, failed = await client.create_events_batch(
                access_token=access_token,
                events=events_kwargs,
                correlation_id=correlation_id,
            )

            WEEKLY_TASKS_TOTAL.labels(provider=provider_name, status="ok").inc()
            WEEKLY_TASKS_CREATED.labels(provider=provider_name).observe(len(created))

            result = CreateWeeklyTasksResult(
                created_events=[e.model_dump_api() for e in created],
                failed_tasks=failed,
                total_requested=len(p.tasks),
                total_created=len(created),
                total_failed=len(failed),
                provider=provider_name,
                week_start=p.week_start,
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
            span.set_attribute("created_count", len(created))
            span.set_attribute("failed_count", len(failed))

            logger.info(
                "create_weekly_tasks.completed",
                provider=provider_name,
                week_start=p.week_start,
                total_requested=len(p.tasks),
                total_created=len(created),
                total_failed=len(failed),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            WEEKLY_TASKS_TOTAL.labels(provider=provider_name, status="error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            WEEKLY_TASKS_TOTAL.labels(provider=provider_name, status="error").inc()
            logger.error(
                "create_weekly_tasks.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc
