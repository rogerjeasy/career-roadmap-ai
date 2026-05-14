"""get_trending_topics — MCP tool handler.

Aggregates signals from all available sources (HackerNews, Reddit,
Twitter/X, Dev.to) for the requested tech stacks and returns a ranked
list of trending topics grouped by tech keyword.

A "topic" is a tech concept (stack keyword + related terms) that appears
frequently across sources with high engagement scores.

JSON-RPC method: ``get_trending_topics``
Params: ``GetTrendingTopicsParams`` (see models.py)
Result: ``TrendingTopicsResult``
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseSocialClient
from models import GetTrendingTopicsParams, SocialSignal, SocialSource, TrendingTopic, TrendingTopicsResult
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

_TOOL_NAME = "get_trending_topics"


async def handle_get_trending_topics(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseSocialClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 60,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_trending_topics") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                p = GetTrendingTopicsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid get_trending_topics parameters",
                    data=exc.errors(),
                )

            span.set_attribute("stacks", ",".join(p.stacks))

            allowed = await rate_limiter.check(user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60)
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            cache_key = p.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Select sources to query ──────────────────────────────────
            active_clients = _select_clients(clients, p.sources)
            if not active_clients:
                raise JsonRpcError(JsonRpcErrorCode.UPSTREAM_ERROR, "No social signal sources configured")

            # ── Fetch from all sources concurrently ──────────────────────
            all_signals = await _fetch_all_sources(active_clients, p.stacks, correlation_id=correlation_id)

            # ── Aggregate into trending topics ───────────────────────────
            topics = _aggregate_topics(all_signals, p.stacks, limit=p.limit)
            sources_queried = list({s.source for s in all_signals})

            result = TrendingTopicsResult(
                topics=[_topic_to_dict(t) for t in topics],
                total_signals_analysed=len(all_signals),
                stacks_queried=p.stacks,
                sources_queried=[s.value for s in sources_queried],
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result)

            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="social_signals",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )
            span.set_attribute("topic_count", len(topics))
            span.set_attribute("total_signals", len(all_signals))

            logger.info(
                "get_trending_topics.completed",
                stacks=p.stacks,
                topic_count=len(topics),
                total_signals=len(all_signals),
                sources=[s.value for s in sources_queried],
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "get_trending_topics.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc


# ── Helpers ───────────────────────────────────────────────────────────────────


def _select_clients(
    clients: dict[str, BaseSocialClient],
    filter_sources: list[SocialSource],
) -> list[BaseSocialClient]:
    if not filter_sources:
        return list(clients.values())
    wanted = {s.value.lower() for s in filter_sources}
    return [c for name, c in clients.items() if c.source.value.lower() in wanted or name in wanted]


async def _fetch_all_sources(
    active_clients: list[BaseSocialClient],
    stacks: list[str],
    *,
    correlation_id: str,
) -> list[SocialSignal]:
    tasks = [
        client.search(stacks, limit=15, correlation_id=correlation_id)
        for client in active_clients
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    signals: list[SocialSignal] = []
    for r in results:
        if isinstance(r, list):
            signals.extend(r)
        elif isinstance(r, Exception):
            logger.warning("get_trending_topics.source_error", error=str(r))
    return signals


def _aggregate_topics(
    signals: list[SocialSignal],
    stacks: list[str],
    limit: int,
) -> list[TrendingTopic]:
    """Group signals by stack keyword and produce ranked TrendingTopic objects."""
    # Count and score signals per stack keyword
    stack_signals: dict[str, list[SocialSignal]] = defaultdict(list)
    for signal in signals:
        for stack in signal.tech_stack:
            stack_lower = stack.lower()
            # Match against requested stacks
            for requested in stacks:
                if requested.lower() == stack_lower or requested.lower() in stack_lower:
                    stack_signals[requested].append(signal)
                    break

    topics: list[TrendingTopic] = []
    for stack, sigs in stack_signals.items():
        if not sigs:
            continue
        total_score = sum(s.score for s in sigs)
        unique_sources = list({s.source for s in sigs})
        top_3 = sorted(sigs, key=lambda s: s.score, reverse=True)[:3]

        topics.append(
            TrendingTopic(
                topic=stack,
                stack=stack,
                signal_count=len(sigs),
                total_score=total_score,
                sources=unique_sources,
                top_signals=[s.model_dump_api() for s in top_3],
            )
        )

    # Rank by composite score: (signal_count * 0.4) + (total_score * 0.6, normalised)
    max_score = max((t.total_score for t in topics), default=1) or 1
    topics.sort(
        key=lambda t: (t.signal_count * 0.4) + (t.total_score / max_score * 0.6),
        reverse=True,
    )
    return topics[:limit]


def _topic_to_dict(topic: TrendingTopic) -> dict[str, Any]:
    return {
        "topic": topic.topic,
        "stack": topic.stack,
        "signal_count": topic.signal_count,
        "total_score": topic.total_score,
        "sources": [s.value for s in topic.sources],
        "top_signals": topic.top_signals,
    }
