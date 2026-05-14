"""Abstract base class for all social signal API clients."""
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

from models import SocialSignal, SocialSource
from observability import (
    SIGNAL_FETCH_DURATION,
    SIGNAL_FETCH_RESULTS,
    SIGNAL_FETCH_TOTAL,
    SIGNAL_SCORE_HISTOGRAM,
    get_tracer,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)
_tracer = get_tracer()


class BaseSocialClient(abc.ABC):
    """Abstract social signals client. Subclasses implement the source logic."""

    source: SocialSource = SocialSource.UNKNOWN

    def __init__(self, *, timeout_seconds: float = 15.0, max_retries: int = 3) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http_client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            f"social_signals.{self.source.value.lower().replace(' ', '_')}",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    async def __aenter__(self) -> "BaseSocialClient":
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
            "User-Agent": "CareerRoadmapAI/1.0 (+https://career-roadmap-ai.com/bot)",
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
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        **kwargs: Any,
    ) -> list[SocialSignal]:
        """Fetch social signals. Returns an empty list on failure."""
        source_name = self.source.value
        with _tracer.start_as_current_span(f"social_signals.{source_name}.search") as span:
            span.set_attribute("source", source_name)
            span.set_attribute("stacks", str(stacks[:5]))
            span.set_attribute("correlation_id", correlation_id)

            t0 = time.monotonic()
            try:
                signals = await self._breaker.call(
                    self._search(stacks, limit, correlation_id=correlation_id, **kwargs)
                )
                latency = time.monotonic() - t0
                SIGNAL_FETCH_TOTAL.labels(source=source_name, status="success").inc()
                SIGNAL_FETCH_DURATION.labels(source=source_name).observe(latency)
                SIGNAL_FETCH_RESULTS.labels(source=source_name).observe(len(signals))
                for s in signals:
                    SIGNAL_SCORE_HISTOGRAM.labels(source=source_name).observe(s.score)
                span.set_attribute("result_count", len(signals))
                logger.info(
                    "social_signals.search_ok",
                    source=source_name,
                    stacks=stacks[:5],
                    count=len(signals),
                    latency_ms=int(latency * 1000),
                    correlation_id=correlation_id,
                )
                return signals
            except CircuitOpenError:
                latency = time.monotonic() - t0
                SIGNAL_FETCH_TOTAL.labels(source=source_name, status="open_circuit").inc()
                SIGNAL_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "social_signals.circuit_open",
                    source=source_name,
                    correlation_id=correlation_id,
                )
                return []
            except asyncio.TimeoutError:
                latency = time.monotonic() - t0
                SIGNAL_FETCH_TOTAL.labels(source=source_name, status="timeout").inc()
                SIGNAL_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "social_signals.search_timeout",
                    source=source_name,
                    correlation_id=correlation_id,
                )
                return []
            except Exception as exc:
                latency = time.monotonic() - t0
                SIGNAL_FETCH_TOTAL.labels(source=source_name, status="error").inc()
                SIGNAL_FETCH_DURATION.labels(source=source_name).observe(latency)
                logger.warning(
                    "social_signals.search_failed",
                    source=source_name,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                return []

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def _search(
        self,
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        **kwargs: Any,
    ) -> list[SocialSignal]: ...

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
