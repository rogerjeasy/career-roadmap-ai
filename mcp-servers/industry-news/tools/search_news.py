"""search_news — MCP tool handler.

Searches tech/AI news from NewsAPI.org (when key is set) and curated RSS feeds.
Results are merged and deduplicated by URL.

JSON-RPC method: ``search_news``
Params: ``SearchNewsParams``
Result: ``SearchNewsResult``
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.newsapi_client import NewsAPIClient
from clients.rss_client import RSSClient
from models import NewsArticle, NewsSource, SearchNewsParams, SearchNewsResult
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

_TOOL_NAME = "search_news"


async def handle_search_news(
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

    with _tracer.start_as_current_span("tool.search_news") as span:
        span.set_attribute("user_id", user_id)

        t0 = time.monotonic()
        try:
            try:
                search_params = SearchNewsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(JsonRpcErrorCode.INVALID_PARAMS, "Invalid parameters", data=exc.errors())

            allowed = await rate_limiter.check(user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60)
            if not allowed:
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rate_limited").inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")

            cache_key = search_params.model_dump()
            cached = await cache.get(_TOOL_NAME, cache_key)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # Determine which sources to query
            use_newsapi = newsapi is not None and (
                not search_params.sources or NewsSource.NEWSAPI in search_params.sources
            )
            use_rss = not search_params.sources or NewsSource.RSS in search_params.sources

            tasks: list[Any] = []
            source_labels: list[str] = []

            if use_newsapi:
                tasks.append(_fetch_newsapi(newsapi, search_params))
                source_labels.append("NewsAPI")
            if use_rss:
                tasks.append(_fetch_rss(rss, search_params))
                source_labels.append("RSS")

            if not tasks:
                raise JsonRpcError(JsonRpcErrorCode.UPSTREAM_ERROR, "No news sources configured")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_articles: list[NewsArticle] = []
            for i, result in enumerate(results):
                if isinstance(result, list):
                    all_articles.extend(result)
                elif isinstance(result, Exception):
                    logger.warning("search_news.source_failed", source=source_labels[i], error=str(result))

            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique: list[NewsArticle] = []
            for a in all_articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    unique.append(a)

            final = unique[: search_params.limit]
            NEWS_ARTICLES_RETURNED.observe(len(final))

            result_dict = SearchNewsResult(
                articles=[a.model_dump_api() for a in final],
                total_count=len(unique),
                query=search_params.query,
                sources_queried=source_labels,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()

            await cache.set(_TOOL_NAME, cache_key, result_dict, ttl=1800)
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
                "search_news.completed",
                query=search_params.query,
                total=len(unique),
                returned=len(final),
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return result_dict

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("search_news.error", error=str(exc), exc_info=True)
            raise JsonRpcError(JsonRpcErrorCode.INTERNAL_ERROR, "Internal error") from exc


async def _fetch_newsapi(client: NewsAPIClient, params: SearchNewsParams) -> list[NewsArticle]:
    t0 = time.monotonic()
    try:
        articles = await client.search(params)
        NEWS_FETCH_TOTAL.labels(source="newsapi", status="ok").inc()
        return articles
    except Exception as exc:
        NEWS_FETCH_TOTAL.labels(source="newsapi", status="error").inc()
        raise
    finally:
        NEWS_FETCH_DURATION.labels(source="newsapi").observe(time.monotonic() - t0)


async def _fetch_rss(client: RSSClient, params: SearchNewsParams) -> list[NewsArticle]:
    t0 = time.monotonic()
    try:
        articles = await client.search(params)
        NEWS_FETCH_TOTAL.labels(source="rss", status="ok").inc()
        return articles
    except Exception as exc:
        NEWS_FETCH_TOTAL.labels(source="rss", status="error").inc()
        raise
    finally:
        NEWS_FETCH_DURATION.labels(source="rss").observe(time.monotonic() - t0)
