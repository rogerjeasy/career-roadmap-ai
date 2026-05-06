"""EventFinder — discover relevant events and online communities via the MCP industry_news server.

Queries the industry_news MCP server concurrently across multiple topics
(target role + top skills), deduplicates results, and ranks by relevance.
Falls back to an empty list when the MCP server is unavailable.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.core.logging import get_logger
from agents.core.observability import (
    NET_EVENT_FETCH_DURATION,
    NET_EVENT_FETCH_TOTAL,
    get_tracer,
)
from agents.networking.mcp_client import MCPClientProtocol
from agents.networking.models import CommunityEvent, EventType

logger = get_logger(__name__)
_tracer = get_tracer("agents.networking.event_finder")

_MAX_EVENTS_PER_TOPIC = 4
_DEFAULT_MAX_TOTAL = 10


class EventFinder:
    """Discover events and communities via MCP industry_news server.

    Inject a custom ``mcp_client`` in tests to control returned data precisely.
    """

    def __init__(
        self,
        mcp_client: MCPClientProtocol,
        max_events: int = _DEFAULT_MAX_TOTAL,
    ) -> None:
        self._mcp = mcp_client
        self._max_events = max_events

    async def find(
        self,
        target_role: str,
        skills: list[str],
        location: str | None,
        *,
        correlation_id: str = "",
    ) -> list[CommunityEvent]:
        """Find relevant events and communities for the user's target role and skills."""
        with _tracer.start_as_current_span("networking.event_find") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("target_role", target_role)
            span.set_attribute("skill_count", len(skills))

            topics = _build_topics(target_role, skills)
            span.set_attribute("topic_count", len(topics))
            t0 = time.monotonic()

            try:
                raw_events = await self._fetch_all_topics(topics, location, correlation_id)
                NET_EVENT_FETCH_TOTAL.labels(status="success").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "networking.event_fetch_failed",
                    error=str(exc),
                    fallback="empty_list",
                    correlation_id=correlation_id,
                )
                NET_EVENT_FETCH_TOTAL.labels(status="error").inc()
                raw_events = []

            duration = time.monotonic() - t0
            NET_EVENT_FETCH_DURATION.observe(duration)

            events = _deduplicate_and_rank(raw_events, target_role, skills)
            events = events[: self._max_events]

            span.set_attribute("events_found", len(events))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "networking.events_found",
                target_role=target_role,
                topics=topics,
                events_found=len(events),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return events

    async def _fetch_all_topics(
        self,
        topics: list[str],
        location: str | None,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        """Fan-out: fetch events for all topics concurrently, merge results."""
        tasks = [
            self._fetch_one_topic(topic, location, correlation_id)
            for topic in topics
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "networking.topic_fetch_failed",
                    error=str(result),
                    correlation_id=correlation_id,
                )
            elif isinstance(result, list):
                merged.extend(result)
        return merged

    async def _fetch_one_topic(
        self,
        topic: str,
        location: str | None,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "topic": topic,
            "limit": _MAX_EVENTS_PER_TOPIC,
        }
        if location:
            params["location"] = location

        result = await self._mcp.call(
            "industry_news",
            "events.search",
            params,
            correlation_id=correlation_id,
        )
        raw_list = result.get("events", [])
        for evt in raw_list:
            evt.setdefault("_search_topic", topic)
        return raw_list


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_topics(target_role: str, skills: list[str]) -> list[str]:
    """Build a deduplicated topic list: target role + top skills."""
    topics = [target_role.lower()]
    for skill in skills[:3]:
        normalized = skill.lower().strip()
        if normalized and normalized not in topics:
            topics.append(normalized)
    return topics


def _deduplicate_and_rank(
    raw_events: list[dict[str, Any]],
    target_role: str,
    skills: list[str],
) -> list[CommunityEvent]:
    """Deduplicate by event_id, compute relevance, and sort descending."""
    seen_ids: set[str] = set()
    events: list[CommunityEvent] = []
    role_lower = target_role.lower()
    skill_set = {s.lower() for s in skills}

    for raw in raw_events:
        event_id = str(raw.get("id", ""))
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)

        skill_tags = [str(t).lower() for t in raw.get("skill_tags", [])]
        relevance = _compute_relevance(skill_tags, role_lower, skill_set)

        try:
            event_type = EventType(raw.get("type", "meetup"))
        except ValueError:
            event_type = EventType.MEETUP

        events.append(
            CommunityEvent(
                event_id=event_id,
                title=str(raw.get("title", "")),
                event_type=event_type,
                platform=str(raw.get("platform", "")),
                skill_tags=skill_tags,
                relevance_score=relevance,
                description=str(raw.get("description", "")),
                url=raw.get("url"),
                date=raw.get("date"),
                location=raw.get("location"),
                is_online=bool(raw.get("is_online", True)),
                source="mcp_industry_news",
            )
        )

    events.sort(key=lambda e: e.relevance_score, reverse=True)
    return events


def _compute_relevance(
    skill_tags: list[str],
    role_lower: str,
    skill_set: set[str],
) -> float:
    """Simple overlap-based relevance score (0-1)."""
    score = 0.0
    for tag in skill_tags:
        if tag in role_lower or role_lower in tag:
            score += 0.4
        elif tag in skill_set:
            score += 0.3
    return round(min(1.0, score), 3)
