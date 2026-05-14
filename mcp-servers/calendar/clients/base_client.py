"""Abstract base class for Google Calendar and Outlook calendar clients."""
from __future__ import annotations

import abc
import asyncio
import os
import sys
import time
from typing import Any

import httpx
import structlog

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import CalendarEvent, CalendarProvider
from observability import (
    EVENT_CREATE_DURATION,
    EVENT_CREATE_TOTAL,
    LIST_FETCH_RESULTS,
    LIST_FETCH_TOTAL,
    get_tracer,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)
_tracer = get_tracer()


class BaseCalendarClient(abc.ABC):
    """Abstract calendar client. Subclasses implement provider-specific logic."""

    provider: CalendarProvider

    def __init__(self, *, timeout_seconds: float = 15.0, max_retries: int = 3) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._breaker = CircuitBreaker(
            f"calendar.{self.provider.value.lower().replace(' ', '_')}",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def create_event(
        self,
        *,
        access_token: str,
        title: str,
        description: str = "",
        start: str,
        end: str,
        timezone: str = "UTC",
        all_day: bool = False,
        location: str = "",
        reminder_minutes: list[int],
        calendar_id: str = "primary",
        color_id: str = "",
        correlation_id: str = "",
    ) -> CalendarEvent:
        """Create a single calendar event. Raises on failure."""
        provider_name = self.provider.value
        with _tracer.start_as_current_span(f"calendar.{provider_name}.create_event") as span:
            span.set_attribute("provider", provider_name)
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                event = await self._breaker.call(
                    self._create_event(
                        access_token=access_token,
                        title=title,
                        description=description,
                        start=start,
                        end=end,
                        timezone=timezone,
                        all_day=all_day,
                        location=location,
                        reminder_minutes=reminder_minutes,
                        calendar_id=calendar_id,
                        color_id=color_id,
                        correlation_id=correlation_id,
                    )
                )
                latency = time.monotonic() - t0
                EVENT_CREATE_TOTAL.labels(provider=provider_name, status="success").inc()
                EVENT_CREATE_DURATION.labels(provider=provider_name).observe(latency)
                span.set_attribute("event_id", event.id)
                logger.info(
                    "calendar.create_event_ok",
                    provider=provider_name,
                    event_id=event.id,
                    latency_ms=int(latency * 1000),
                    correlation_id=correlation_id,
                )
                return event
            except CircuitOpenError as exc:
                latency = time.monotonic() - t0
                EVENT_CREATE_TOTAL.labels(provider=provider_name, status="open_circuit").inc()
                EVENT_CREATE_DURATION.labels(provider=provider_name).observe(latency)
                logger.warning(
                    "calendar.circuit_open",
                    provider=provider_name,
                    correlation_id=correlation_id,
                )
                raise
            except httpx.HTTPStatusError as exc:
                latency = time.monotonic() - t0
                status = "auth_error" if exc.response.status_code in (401, 403) else "http_error"
                EVENT_CREATE_TOTAL.labels(provider=provider_name, status=status).inc()
                EVENT_CREATE_DURATION.labels(provider=provider_name).observe(latency)
                logger.warning(
                    "calendar.create_event_http_error",
                    provider=provider_name,
                    status_code=exc.response.status_code,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                raise
            except Exception as exc:
                latency = time.monotonic() - t0
                EVENT_CREATE_TOTAL.labels(provider=provider_name, status="error").inc()
                EVENT_CREATE_DURATION.labels(provider=provider_name).observe(latency)
                logger.warning(
                    "calendar.create_event_failed",
                    provider=provider_name,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                raise

    async def create_events_batch(
        self,
        *,
        access_token: str,
        events: list[dict[str, Any]],
        correlation_id: str = "",
    ) -> tuple[list[CalendarEvent], list[dict[str, Any]]]:
        """Create multiple events concurrently (max 5 parallel). Returns (created, failed)."""
        created: list[CalendarEvent] = []
        failed: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(5)

        async def _try_create(event_kwargs: dict[str, Any]) -> CalendarEvent | None:
            day_of_week = event_kwargs.pop("_day_of_week", -1)
            title = event_kwargs.get("title", "")
            async with semaphore:
                try:
                    return await self.create_event(
                        **event_kwargs,
                        access_token=access_token,
                        correlation_id=correlation_id,
                    )
                except Exception as exc:
                    failed.append(
                        {"title": title, "day_of_week": day_of_week, "error": str(exc)}
                    )
                    return None

        results = await asyncio.gather(*[_try_create(ev) for ev in events])
        created = [r for r in results if r is not None]
        return created, failed

    async def list_upcoming(
        self,
        *,
        access_token: str,
        max_results: int = 10,
        time_min: str | None = None,
        time_max: str | None = None,
        timezone: str = "UTC",
        calendar_id: str = "primary",
        correlation_id: str = "",
    ) -> list[CalendarEvent]:
        """List upcoming events. Raises on failure."""
        provider_name = self.provider.value
        with _tracer.start_as_current_span(f"calendar.{provider_name}.list_upcoming") as span:
            span.set_attribute("provider", provider_name)
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                events = await self._breaker.call(
                    self._list_upcoming(
                        access_token=access_token,
                        max_results=max_results,
                        time_min=time_min,
                        time_max=time_max,
                        timezone=timezone,
                        calendar_id=calendar_id,
                        correlation_id=correlation_id,
                    )
                )
                latency = time.monotonic() - t0
                LIST_FETCH_TOTAL.labels(provider=provider_name, status="success").inc()
                LIST_FETCH_RESULTS.labels(provider=provider_name).observe(len(events))
                span.set_attribute("result_count", len(events))
                logger.info(
                    "calendar.list_upcoming_ok",
                    provider=provider_name,
                    count=len(events),
                    latency_ms=int(latency * 1000),
                    correlation_id=correlation_id,
                )
                return events
            except CircuitOpenError:
                latency = time.monotonic() - t0
                LIST_FETCH_TOTAL.labels(provider=provider_name, status="open_circuit").inc()
                logger.warning(
                    "calendar.list_upcoming_circuit_open",
                    provider=provider_name,
                    correlation_id=correlation_id,
                )
                raise
            except Exception as exc:
                latency = time.monotonic() - t0
                LIST_FETCH_TOTAL.labels(provider=provider_name, status="error").inc()
                logger.warning(
                    "calendar.list_upcoming_failed",
                    provider=provider_name,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                raise

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def _create_event(
        self,
        *,
        access_token: str,
        title: str,
        description: str,
        start: str,
        end: str,
        timezone: str,
        all_day: bool,
        location: str,
        reminder_minutes: list[int],
        calendar_id: str,
        color_id: str,
        correlation_id: str,
    ) -> CalendarEvent: ...

    @abc.abstractmethod
    async def _list_upcoming(
        self,
        *,
        access_token: str,
        max_results: int,
        time_min: str | None,
        time_max: str | None,
        timezone: str,
        calendar_id: str,
        correlation_id: str,
    ) -> list[CalendarEvent]: ...

    # ── HTTP helpers (create per-call client — no persistent connection for OAuth tokens) ──

    async def _get(
        self, url: str, *, headers: dict[str, str], **kwargs: Any
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        ) as client:
            resp = await client.get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any],
        **kwargs: Any,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        ) as client:
            resp = await client.post(url, headers=headers, json=json_body, **kwargs)
            resp.raise_for_status()
            return resp
