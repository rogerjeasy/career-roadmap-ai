"""Abstract base class for all salary benchmark data clients."""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import ExperienceLevel, GetSalaryRangeParams, SalaryDataPoint, SalarySource
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)


class BaseSalaryClient(ABC):
    """Common HTTP plumbing + retry + circuit breaker for salary data sources."""

    source: SalarySource

    def __init__(self, *, timeout_seconds: float = 20.0, max_retries: int = 3) -> None:
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            f"salary_benchmark.{self.source.value.lower().replace(' ', '_')}",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "CareerRoadmapAI/1.0"}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._default_headers(),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        reraise=True,
    )
    async def _get(self, url: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        response = await self._get_client().get(url, params=params)
        response.raise_for_status()
        return response

    async def fetch(self, params: GetSalaryRangeParams) -> list[SalaryDataPoint]:
        try:
            return await self._breaker.call(self._fetch(params))
        except CircuitOpenError:
            logger.warning(
                "salary_client.circuit_open",
                source=self.source.value,
                role=params.role,
            )
            return []
        except Exception as exc:
            logger.warning(
                "salary_client.fetch_failed",
                source=self.source.value,
                error=str(exc),
            )
            return []

    @abstractmethod
    async def _fetch(self, params: GetSalaryRangeParams) -> list[SalaryDataPoint]: ...
