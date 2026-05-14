"""Abstract base class for all course catalogue API clients."""
from __future__ import annotations

import abc
import asyncio
import os
import sys
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

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import Course, CourseSource, SearchCoursesParams
from observability import (
    COURSE_FETCH_DURATION,
    COURSE_FETCH_RESULTS,
    COURSE_FETCH_TOTAL,
    get_tracer,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)
_tracer = get_tracer()


class BaseCourseClient(abc.ABC):
    """Abstract course catalogue client. Subclasses implement source-specific logic."""

    source: CourseSource = CourseSource.UNKNOWN

    def __init__(self, *, timeout_seconds: float = 15.0, max_retries: int = 3) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http_client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            f"course_catalogue.{self.source.value.lower().replace(' ', '_')}",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    async def __aenter__(self) -> "BaseCourseClient":
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers=self._default_headers(),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http_client and not self._http_client.is_closed:
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
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
                headers=self._default_headers(),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client

    # ── Public interface ──────────────────────────────────────────────────────

    async def search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        source_name = self.source.value
        with _tracer.start_as_current_span(f"course_catalogue.{source_name}.search") as span:
            span.set_attribute("source", source_name)
            span.set_attribute("skill", params.skill)
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                courses = await self._breaker.call(
                    self._search(params, correlation_id=correlation_id)
                )
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
            except CircuitOpenError:
                latency = time.monotonic() - t0
                COURSE_FETCH_TOTAL.labels(source=source_name, status="open_circuit").inc()
                COURSE_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "course_catalogue.circuit_open",
                    source=source_name,
                    skill=params.skill,
                    correlation_id=correlation_id,
                )
                return []
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
        try:
            return await self._breaker.call(
                self._get_detail(course_id, correlation_id=correlation_id)
            )
        except (CircuitOpenError, Exception) as exc:
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
    ) -> list[Course]: ...

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
