"""TrendFetcher — retrieves GitHub trend signals and social signals via MCP.

Both sources are fetched concurrently. Either list may be empty if the
corresponding MCP server call fails — the signal processor handles partial data.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.core.logging import get_logger
from agents.core.observability import (
    MARKET_TREND_FETCH_DURATION,
    MARKET_TREND_FETCH_TOTAL,
    get_tracer,
)
from agents.market_intelligence.mcp_client import MCPClientProtocol

logger = get_logger(__name__)
_tracer = get_tracer("agents.market_intelligence.trend_fetcher")


class TrendFetcher:
    """Fetches GitHub and social trend data from MCP servers in parallel.

    Returns raw dicts so SignalProcessor can aggregate them without
    being coupled to individual source formats.
    """

    def __init__(self, mcp_client: MCPClientProtocol) -> None:
        self._client = mcp_client

    async def fetch(
        self,
        tech_stack_hints: list[str],
        *,
        correlation_id: str = "",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(github_trends, social_signals)`` fetched concurrently.

        Each list is raw MCP tool data normalised to a flat list of dicts.
        """
        with _tracer.start_as_current_span("market.trend_fetch") as span:
            span.set_attribute("hint_count", len(tech_stack_hints))
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            github_raw, social_raw = await asyncio.gather(
                self._fetch_github(tech_stack_hints, correlation_id),
                self._fetch_social(tech_stack_hints, correlation_id),
            )

            latency = time.monotonic() - t0
            MARKET_TREND_FETCH_DURATION.observe(latency)
            span.set_attribute("github_item_count", len(github_raw))
            span.set_attribute("social_item_count", len(social_raw))
            span.set_attribute("latency_ms", int(latency * 1000))

            logger.info(
                "market.trends_fetched",
                github_item_count=len(github_raw),
                social_item_count=len(social_raw),
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            return github_raw, social_raw

    async def _fetch_github(
        self,
        hints: list[str],
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        try:
            raw = await self._client.call(
                "github_trends",
                "get_trending",
                {"topics": hints, "limit": 10},
                correlation_id=correlation_id,
            )
            items: list[dict[str, Any]] = list(raw.get("trending_repos", []))
            # Synthesise topic-level entries from trending_topics array
            for topic in raw.get("trending_topics", []):
                items.append({"name": str(topic), "topic": str(topic), "stars_this_week": 0})
            MARKET_TREND_FETCH_TOTAL.labels(status="success", source="github_trends").inc()
            return items
        except Exception as exc:
            MARKET_TREND_FETCH_TOTAL.labels(status="error", source="github_trends").inc()
            logger.warning(
                "market.github_trends_failed",
                error=str(exc),
                correlation_id=correlation_id,
            )
            return []

    async def _fetch_social(
        self,
        hints: list[str],
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        try:
            raw = await self._client.call(
                "social_signals",
                "get_signals",
                {"topics": hints, "sources": ["hackernews", "reddit"]},
                correlation_id=correlation_id,
            )
            signals: list[dict[str, Any]] = []
            for item in raw.get("hackernews", []):
                signals.append({**item, "_source": "hackernews"})
            for item in raw.get("reddit", []):
                signals.append({**item, "_source": "reddit"})
            for topic in raw.get("trending_topics", []):
                signals.append({"title": str(topic), "points": 0, "_source": "social_aggregate"})
            MARKET_TREND_FETCH_TOTAL.labels(status="success", source="social_signals").inc()
            return signals
        except Exception as exc:
            MARKET_TREND_FETCH_TOTAL.labels(status="error", source="social_signals").inc()
            logger.warning(
                "market.social_signals_failed",
                error=str(exc),
                correlation_id=correlation_id,
            )
            return []
