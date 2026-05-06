"""JobBoardFetcher — retrieves live job postings via the MCP job_board server.

Stateless. Inject a different MCPClientProtocol to control data in tests.
Failures are caught; an empty list is returned so the rest of the pipeline
can still produce a partial result.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from agents.core.logging import get_logger
from agents.core.observability import (
    MARKET_JOB_FETCH_DURATION,
    MARKET_JOB_FETCH_TOTAL,
    get_tracer,
)
from agents.market_intelligence.mcp_client import MCPClientProtocol
from agents.market_intelligence.models import JobPosting

logger = get_logger(__name__)
_tracer = get_tracer("agents.market_intelligence.job_board_fetcher")


class JobBoardFetcher:
    """Fetches live job postings from the MCP job_board server."""

    def __init__(self, mcp_client: MCPClientProtocol) -> None:
        self._client = mcp_client

    async def fetch(
        self,
        role: str,
        country: str,
        limit: int = 20,
        *,
        correlation_id: str = "",
    ) -> list[JobPosting]:
        """Return up to ``limit`` live postings for ``role`` in ``country``."""
        with _tracer.start_as_current_span("market.job_board_fetch") as span:
            span.set_attribute("role", role)
            span.set_attribute("country", country)
            span.set_attribute("limit", limit)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                raw = await self._client.call(
                    "job_board",
                    "search_jobs",
                    {"role": role, "country": country, "limit": limit},
                    correlation_id=correlation_id,
                )
                postings = _parse_postings(raw)
                MARKET_JOB_FETCH_TOTAL.labels(status="success").inc()
            except Exception as exc:
                MARKET_JOB_FETCH_TOTAL.labels(status="error").inc()
                logger.warning(
                    "market.job_board_fetch_failed",
                    role=role,
                    country=country,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                postings = []

            latency = time.monotonic() - t0
            MARKET_JOB_FETCH_DURATION.observe(latency)
            span.set_attribute("posting_count", len(postings))
            span.set_attribute("latency_ms", int(latency * 1000))

            logger.info(
                "market.job_board_fetched",
                role=role,
                country=country,
                posting_count=len(postings),
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            return postings


def _parse_postings(raw: dict[str, Any]) -> list[JobPosting]:
    postings: list[JobPosting] = []
    for item in raw.get("postings", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue

        posted_date: date | None = None
        if posted_str := item.get("posted_date"):
            try:
                posted_date = date.fromisoformat(str(posted_str)[:10])
            except (ValueError, TypeError):
                pass

        required_skills = [str(s) for s in item.get("required_skills", []) if s]

        postings.append(
            JobPosting(
                title=title,
                company=str(item.get("company", "Unknown")),
                location=str(item.get("location", "")),
                required_skills=required_skills,
                source=str(item.get("source", "unknown")),
                posted_date=posted_date,
                salary_min=_to_int(item.get("salary_min")),
                salary_max=_to_int(item.get("salary_max")),
                currency=str(item.get("currency", "USD")),
                url=item.get("url") or None,
            )
        )
    return postings


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
