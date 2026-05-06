"""SalaryFetcher — retrieves salary benchmarks via the MCP salary_benchmark server.

Returns None on failure so callers can treat missing salary data as optional.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from agents.core.logging import get_logger
from agents.core.observability import (
    MARKET_SALARY_FETCH_DURATION,
    MARKET_SALARY_FETCH_TOTAL,
    get_tracer,
)
from agents.market_intelligence.mcp_client import MCPClientProtocol
from agents.market_intelligence.models import SalaryBenchmark

logger = get_logger(__name__)
_tracer = get_tracer("agents.market_intelligence.salary_fetcher")


class SalaryFetcher:
    """Fetches compensation benchmarks from the MCP salary_benchmark server."""

    def __init__(self, mcp_client: MCPClientProtocol) -> None:
        self._client = mcp_client

    async def fetch(
        self,
        role: str,
        country: str,
        *,
        correlation_id: str = "",
    ) -> SalaryBenchmark | None:
        """Return a salary benchmark for ``role`` in ``country``, or None on failure."""
        with _tracer.start_as_current_span("market.salary_fetch") as span:
            span.set_attribute("role", role)
            span.set_attribute("country", country)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                raw = await self._client.call(
                    "salary_benchmark",
                    "get_salary",
                    {"role": role, "country": country},
                    correlation_id=correlation_id,
                )
                benchmark = _parse_salary(role, country, raw)
                MARKET_SALARY_FETCH_TOTAL.labels(status="success").inc()
            except Exception as exc:
                MARKET_SALARY_FETCH_TOTAL.labels(status="error").inc()
                logger.warning(
                    "market.salary_fetch_failed",
                    role=role,
                    country=country,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                benchmark = None

            latency = time.monotonic() - t0
            MARKET_SALARY_FETCH_DURATION.observe(latency)
            span.set_attribute("has_data", benchmark is not None)
            span.set_attribute("latency_ms", int(latency * 1000))

            logger.info(
                "market.salary_fetched",
                role=role,
                country=country,
                has_data=benchmark is not None,
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            return benchmark


def _parse_salary(role: str, country: str, raw: dict[str, Any]) -> SalaryBenchmark | None:
    if not raw:
        return None

    freshness_date: date | None = None
    if freshness_str := raw.get("freshness_date"):
        try:
            freshness_date = date.fromisoformat(str(freshness_str)[:10])
        except (ValueError, TypeError):
            pass

    return SalaryBenchmark(
        role=str(raw.get("role", role)),
        country=str(raw.get("country", country)),
        median_annual=_to_int(raw.get("median_annual")),
        p25_annual=_to_int(raw.get("p25_annual")),
        p75_annual=_to_int(raw.get("p75_annual")),
        currency=str(raw.get("currency", "USD")),
        source=str(raw.get("source", "unknown")),
        freshness_date=freshness_date,
    )


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
