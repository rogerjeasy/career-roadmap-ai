"""Abstract base class for all job board API clients.

Every client:
- Wraps httpx.AsyncClient with a shared timeout and retry policy (tenacity)
- Guards upstream calls with a per-source circuit breaker
- Records per-source Prometheus metrics on every fetch
- Emits structured log events on success/failure
- Returns normalised ``JobPosting`` objects — never raw dicts

Subclasses implement ``search()``, ``get_detail()``, and optionally
``get_trending_roles()``.
"""
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

from models import JobPosting, JobSource, SearchJobsParams, TrendingRole
from observability import (
    JOB_FETCH_DURATION,
    JOB_FETCH_RESULTS,
    JOB_FETCH_TOTAL,
    get_tracer,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)
_tracer = get_tracer()


class BaseJobBoardClient(abc.ABC):
    """Abstract job board client. Subclasses implement the source-specific logic."""

    source: JobSource = JobSource.UNKNOWN

    def __init__(self, *, timeout_seconds: float = 15.0, max_retries: int = 3) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http_client: httpx.AsyncClient | None = None
        # One circuit breaker per source — shared across all instances of the subclass
        self._breaker = CircuitBreaker(
            f"job_board.{self.source.value.lower().replace(' ', '_')}",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    async def __aenter__(self) -> "BaseJobBoardClient":
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers=self._default_headers(),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
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
        params: SearchJobsParams,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        """Fetch job postings from this source. Returns an empty list on failure."""
        source_name = self.source.value
        with _tracer.start_as_current_span(f"job_board.{source_name}.search") as span:
            span.set_attribute("source", source_name)
            span.set_attribute("role", params.role)
            span.set_attribute("country", params.country)
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                postings = await self._breaker.call(
                    self._search(params, correlation_id=correlation_id)
                )
                latency = time.monotonic() - t0
                JOB_FETCH_TOTAL.labels(source=source_name, status="success").inc()
                JOB_FETCH_DURATION.labels(source=source_name).observe(latency)
                JOB_FETCH_RESULTS.labels(source=source_name).observe(len(postings))
                span.set_attribute("result_count", len(postings))
                logger.info(
                    "job_board.search_ok",
                    source=source_name,
                    role=params.role,
                    country=params.country,
                    count=len(postings),
                    latency_ms=int(latency * 1000),
                    correlation_id=correlation_id,
                )
                return postings
            except CircuitOpenError:
                latency = time.monotonic() - t0
                JOB_FETCH_TOTAL.labels(source=source_name, status="open_circuit").inc()
                JOB_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "job_board.circuit_open",
                    source=source_name,
                    role=params.role,
                    correlation_id=correlation_id,
                )
                return []
            except asyncio.TimeoutError:
                latency = time.monotonic() - t0
                JOB_FETCH_TOTAL.labels(source=source_name, status="timeout").inc()
                JOB_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "job_board.search_timeout",
                    source=source_name,
                    role=params.role,
                    correlation_id=correlation_id,
                )
                return []
            except Exception as exc:
                latency = time.monotonic() - t0
                JOB_FETCH_TOTAL.labels(source=source_name, status="error").inc()
                JOB_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "job_board.search_failed",
                    source=source_name,
                    role=params.role,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                return []

    async def get_detail(self, job_id: str, *, country: str = "CH", correlation_id: str = "") -> JobPosting | None:
        """Fetch full job detail by ID. Returns None on failure."""
        try:
            return await self._breaker.call(
                self._get_detail(job_id, country=country, correlation_id=correlation_id)
            )
        except (CircuitOpenError, Exception) as exc:
            logger.warning(
                "job_board.detail_failed",
                source=self.source.value,
                job_id=job_id,
                error=str(exc),
                correlation_id=correlation_id,
            )
            return None

    async def get_trending_roles(
        self,
        country: str,
        limit: int = 10,
        *,
        correlation_id: str = "",
    ) -> list[TrendingRole]:
        """Fetch trending job roles. Returns an empty list on failure."""
        try:
            return await self._breaker.call(
                self._get_trending_roles(country, limit, correlation_id=correlation_id)
            )
        except (CircuitOpenError, Exception) as exc:
            logger.warning(
                "job_board.trending_failed",
                source=self.source.value,
                country=country,
                error=str(exc),
                correlation_id=correlation_id,
            )
            return []

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def _search(
        self,
        params: SearchJobsParams,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        """Source-specific search logic. May raise — caller catches."""

    async def _get_detail(
        self,
        job_id: str,
        *,
        country: str = "CH",
        correlation_id: str = "",
    ) -> JobPosting | None:
        return None

    async def _get_trending_roles(
        self,
        country: str,
        limit: int,
        *,
        correlation_id: str = "",
    ) -> list[TrendingRole]:
        return []

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
