"""Abstract base class for all course catalogue API clients.

Every client:
- Wraps httpx.AsyncClient with shared timeout and retry policy (tenacity)
- Records per-source Prometheus metrics on every fetch
- Emits structured log events on success / failure
- Returns normalised ``Course`` objects — never raw dicts

Subclasses implement ``_search()`` and optionally ``_get_detail()``.
"""
from __future__ import annotations

import abc
import asyncio
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models import Course, CourseSource, SearchCoursesParams
from observability import (
    COURSE_FETCH_DURATION,
    COURSE_FETCH_RESULTS,
    COURSE_FETCH_TOTAL,
    get_tracer,
)

logger = structlog.get_logger(__name__)
_tracer = get_tracer()


class BaseCourseClient(abc.ABC):
    """Abstract course catalogue client. Subclasses implement source-specific logic."""

    source: CourseSource = CourseSource.UNKNOWN

    def __init__(self, *, timeout_seconds: float = 15.0, max_retries: int = 3) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseCourseClient":
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers=self._default_headers(),
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http_client:
            await self._http_client.aclose()

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (compatible; CareerRoadmapAI/1.0; "
                "+https://career-roadmap-ai.com/bot)"
            ),
        }

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            raise RuntimeError("Client not started — use `async with` context manager")
        return self._http_client

    # ── Public interface ──────────────────────────────────────────────────────

    async def search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        """Fetch courses from this source. Returns an empty list on failure."""
        source_name = self.source.value
        with _tracer.start_as_current_span(f"course_catalogue.{source_name}.search") as span:
            span.set_attribute("source", source_name)
            span.set_attribute("skill", params.skill)
            span.set_attribute("level", params.level)
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                courses = await self._search(params, correlation_id=correlation_id)
                latency = time.monotonic() - t0
                COURSE_FETCH_TOTAL.labels(source=source_name, status="success").inc()
                COURSE_FETCH_DURATION.labels(source=source_name).observe(latency)
                COURSE_FETCH_RESULTS.labels(source=source_name).observe(len(courses))
                span.set_attribute("result_count", len(courses))
                logger.info(
                    "course_catalogue.search_ok",
                    source=source_name,
                    skill=params.skill,
                    count=len(courses),
                    latency_ms=int(latency * 1000),
                    correlation_id=correlation_id,
                )
                return courses
            except asyncio.TimeoutError:
                latency = time.monotonic() - t0
                COURSE_FETCH_TOTAL.labels(source=source_name, status="timeout").inc()
                COURSE_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "course_catalogue.search_timeout",
                    source=source_name,
                    skill=params.skill,
                    correlation_id=correlation_id,
                )
                return []
            except Exception as exc:
                latency = time.monotonic() - t0
                COURSE_FETCH_TOTAL.labels(source=source_name, status="error").inc()
                COURSE_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "course_catalogue.search_failed",
                    source=source_name,
                    skill=params.skill,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                return []

    async def get_detail(self, course_id: str, *, correlation_id: str = "") -> Course | None:
        """Fetch full course detail by ID. Returns None on failure."""
        try:
            return await self._get_detail(course_id, correlation_id=correlation_id)
        except Exception as exc:
            logger.warning(
                "course_catalogue.detail_failed",
                source=self.source.value,
                course_id=course_id,
                error=str(exc),
                correlation_id=correlation_id,
            )
            return None

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        """Source-specific search logic. May raise — caller catches."""

    async def _get_detail(
        self,
        course_id: str,
        *,
        correlation_id: str = "",
    ) -> Course | None:
        return None

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        resp = await self._client.post(url, **kwargs)
        resp.raise_for_status()
        return resp
