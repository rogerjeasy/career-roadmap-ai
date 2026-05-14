"""get_weekly_digest — MCP tool handler.

Aggregates tech/AI news from the past 7 days into a structured weekly digest,
grouped by topic. Each section contains a brief summary and top articles.

JSON-RPC method: ``get_weekly_digest``
Params: ``GetWeeklyDigestParams``
Result: WeeklyDigest (serialised dict)
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.newsapi_client import NewsAPIClient
from clients.rss_client import RSSClient
from models import DigestSection, GetWeeklyDigestParams, NewsArticle, NewsSource, WeeklyDigest
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    NEWS_ARTICLES_RETURNED,
    NEWS_FETCH_DURATION,
    NEWS_FETCH_TOTAL,
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

_TOOL_NAME = "get_weekly_digest"

_DEFAULT_TOPICS = [
    "machine learning",
    "artificial intelligence",
    "software engineering",
    "career",
    "open source",
]

_TOPIC_QUERIES: dict[str, str] = {
    "machine learning": "machine learning OR deep learning OR neural network",
    "artificial intelligence": "artificial intelligence OR AI OR LLM OR GPT",
    "software engineering": "software engineering OR developer OR backend OR API",
    "career": "tech career OR job market OR hiring OR remote work",
    "open source": "open source OR GitHub OR contribution",
    "python": "python programming OR python library OR pytorch OR fastapi",
    "data science": "data science OR data engineering OR analytics OR visualization",
}


async def handle_get_weekly_digest(
    params: dict[str, Any],
    request: Request,
    newsapi: NewsAPIClient | None,
    rss: RSSClient,
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_weekly_digest") as span:
        span.set_attribute("user_id", user_id)

        t0 = time.monotonic()
        try:
            try:
                digest_params = GetWeeklyDigestParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(JsonRpcErrorCode.INVALID_PARAMS, "Invalid parameters", data=exc.errors())

            allowed = await rate_limiter.check(user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60)
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            cache_key = digest_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            topics = digest_params.topics or _DEFAULT_TOPICS

            # Fetch articles from RSS feeds first (always available)
            rss_t0 = time.monotonic()
            try:
                rss_articles = await rss.get_digest_feeds(topics, limit=100)
                NEWS_FETCH_TOTAL.labels(source="rss", status="ok").inc()
            except Exception as exc:
                NEWS_FETCH_TOTAL.labels(source="rss", status="error").inc()
                rss_articles = []
                logger.warning("get_weekly_digest.rss_failed", error=str(exc))
            finally:
                NEWS_FETCH_DURATION.labels(source="rss").observe(time.monotonic() - rss_t0)

            # Optionally enrich with NewsAPI
            newsapi_articles: list[NewsArticle] = []
            if newsapi:
                from models import SearchNewsParams
                for topic in topics[:3]:  # limit NewsAPI calls
                    query = _TOPIC_QUERIES.get(topic.lower(), topic)
                    newsapi_t0 = time.monotonic()
                    try:
                        results = await newsapi.search(SearchNewsParams(query=query, limit=10, language=digest_params.language))
                        newsapi_articles.extend(results)
                        NEWS_FETCH_TOTAL.labels(source="newsapi", status="ok").inc()
                    except Exception as exc:
                        NEWS_FETCH_TOTAL.labels(source="newsapi", status="error").inc()
                        logger.warning("get_weekly_digest.newsapi_topic_failed", topic=topic, error=str(exc))
                    finally:
                        NEWS_FETCH_DURATION.labels(source="newsapi").observe(time.monotonic() - newsapi_t0)

            all_articles = rss_articles + newsapi_articles
            NEWS_ARTICLES_RETURNED.observe(len(all_articles))

            # Group into sections
            sections = _build_sections(topics, all_articles)

            sources_queried = ["RSS"]
            if newsapi:
                sources_queried.append("NewsAPI")

            digest = WeeklyDigest(
                sections=sections,
                total_articles=len(all_articles),
                sources_queried=sources_queried,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

            result_dict = digest.model_dump_api()

            await cache.set(_TOOL_NAME, cache_key, result_dict, ttl=3600)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="industry_news",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )

            logger.info(
                "get_weekly_digest.completed",
                topics=topics,
                sections=len(sections),
                total_articles=len(all_articles),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result_dict

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("get_weekly_digest.error", error=str(exc), exc_info=True)
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc


def _build_sections(topics: list[str], articles: list[NewsArticle]) -> list[DigestSection]:
    sections: list[DigestSection] = []
    used_urls: set[str] = set()

    for topic in topics:
        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        relevant = [
            a for a in articles
            if a.url not in used_urls
            and any(
                w in (a.title or "").lower() or w in (a.description or "").lower()
                for w in topic_words
                if len(w) > 2  # include 3-letter tech terms (llm, api, ai, etc.)
            )
        ][:5]

        if not relevant:
            continue

        for a in relevant:
            used_urls.add(a.url)

        summary = _make_summary(topic, relevant)
        sections.append(
            DigestSection(
                topic=topic.title(),
                summary=summary,
                articles=[a.model_dump_api() for a in relevant],
            )
        )

    return sections


def _make_summary(topic: str, articles: list[NewsArticle]) -> str:
    titles = [a.title for a in articles[:3] if a.title]
    if not titles:
        return f"No recent articles found for {topic}."
    count = len(articles)
    sample = "; ".join(titles[:2])
    return f"{count} article{'s' if count != 1 else ''} this week on {topic}. Highlights: {sample}."
