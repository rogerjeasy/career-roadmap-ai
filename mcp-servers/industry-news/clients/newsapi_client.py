"""NewsAPI.org client with circuit breaker.

Free developer plan: 100 requests/day, delayed articles, no commercial use.
Paid plans available for production.

API docs: https://newsapi.org/docs
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import NewsArticle, NewsSource, SearchNewsParams
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)


class NewsAPIClient:
    """Fetches news articles from NewsAPI.org with circuit breaker protection."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://newsapi.org/v2",
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            "industry_news.newsapi",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "CareerRoadmapAI/1.0",
                    "X-Api-Key": self._api_key,
                },
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        resp = await self._get_client().get(f"{self._base_url}{path}", params=params)
        resp.raise_for_status()
        return resp

    async def search(self, params: SearchNewsParams) -> list[NewsArticle]:
        query_params: dict[str, Any] = {
            "q": params.query,
            "language": params.language,
            "sortBy": "publishedAt",
            "pageSize": min(params.limit, 100),
        }
        if params.from_date:
            query_params["from"] = params.from_date

        async def _fetch() -> list[NewsArticle]:
            try:
                resp = await self._get("/everything", query_params)
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 426:
                    logger.warning("newsapi.plan_limit", hint="Upgrade NewsAPI plan for full access")
                    return []
                raise

            articles: list[NewsArticle] = []
            for item in data.get("articles", []):
                article = _parse_article(item)
                if article:
                    articles.append(article)
                if len(articles) >= params.limit:
                    break
            return articles

        try:
            return await self._breaker.call(_fetch())
        except CircuitOpenError:
            logger.warning("newsapi.circuit_open")
            return []
        except Exception as exc:
            logger.warning("newsapi.fetch_failed", error=str(exc))
            return []

    async def top_headlines(
        self, category: str = "technology", language: str = "en", limit: int = 20
    ) -> list[NewsArticle]:
        async def _fetch() -> list[NewsArticle]:
            resp = await self._get(
                "/top-headlines",
                {"category": category, "language": language, "pageSize": min(limit, 100)},
            )
            data = resp.json()
            return [a for item in data.get("articles", []) if (a := _parse_article(item))][:limit]

        try:
            return await self._breaker.call(_fetch())
        except (CircuitOpenError, Exception) as exc:
            logger.warning("newsapi.top_headlines_failed", error=str(exc))
            return []


def _parse_article(item: dict[str, Any]) -> NewsArticle | None:
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not url or title == "[Removed]":
        return None

    article_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    source = item.get("source") or {}
    source_name = str(source.get("name") or "Unknown")

    return NewsArticle(
        id=article_id,
        title=title,
        description=str(item.get("description") or "")[:500] or None,
        content=str(item.get("content") or "")[:2000] or None,
        url=url,
        source_name=source_name,
        news_source=NewsSource.NEWSAPI,
        published_at=str(item.get("publishedAt") or "") or None,
        author=str(item.get("author") or "") or None,
        image_url=str(item.get("urlToImage") or "") or None,
    )
