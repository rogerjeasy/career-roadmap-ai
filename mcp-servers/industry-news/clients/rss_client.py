"""RSS feed client for tech/AI news.

Fetches from a curated list of high-quality RSS feeds. No API key required.
Uses feedparser for robust RSS/Atom parsing.

Configured feeds cover: AI/ML research, tech industry news, software
engineering, and Swiss tech market.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import httpx
import structlog

from models import NewsArticle, NewsSource, SearchNewsParams

logger = structlog.get_logger(__name__)

# Curated RSS/Atom feed URLs — no API key required.
# Feed status verified 2026-05-14:
#   The Batch (deeplearning.ai) — no public RSS at any URL, removed
#   Anthropic News — no public RSS, removed
#   Swiss ICT feed path was /news/feed/ (404), corrected to /feed/
#   Replaced with: Last Week In AI, TechCrunch AI
_FEEDS: dict[str, str] = {
    "HackerNews": "https://news.ycombinator.com/rss",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "MIT Technology Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "Last Week In AI": "https://lastweekin.ai/feed",
    "Towards Data Science": "https://towardsdatascience.com/feed",
    "Papers With Code": "https://paperswithcode.com/latest.rss",
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "InfoQ ML": "https://feed.infoq.com/ai-ml-data-eng/",
    "Swiss ICT": "https://www.swissict.ch/feed/",
}

_TOPIC_FEEDS: dict[str, list[str]] = {
    "machine learning": ["Google AI Blog", "MIT Technology Review AI", "Last Week In AI", "Papers With Code"],
    "deep learning": ["Google AI Blog", "Papers With Code", "Last Week In AI"],
    "artificial intelligence": ["Google AI Blog", "OpenAI Blog", "TechCrunch AI", "MIT Technology Review AI"],
    "ai": ["Google AI Blog", "OpenAI Blog", "TechCrunch AI", "MIT Technology Review AI"],
    "llm": ["Google AI Blog", "OpenAI Blog", "Last Week In AI", "TechCrunch AI"],
    "software engineering": ["HackerNews", "InfoQ ML", "Towards Data Science"],
    "career": ["HackerNews", "Towards Data Science"],
    "python": ["Towards Data Science", "InfoQ ML"],
    "data science": ["Towards Data Science", "Papers With Code"],
    "switzerland": ["Swiss ICT", "HackerNews"],
}


class RSSClient:
    """Fetches and parses RSS/Atom feeds."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_concurrent: int = 5,
    ) -> None:
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_concurrent = max_concurrent
        self._http_client: httpx.AsyncClient | None = None

    def _get_http(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": "CareerRoadmapAI/1.0 (RSS reader)"},
                follow_redirects=True,
            )
        return self._http_client

    async def search(self, params: SearchNewsParams) -> list[NewsArticle]:
        query_lower = params.query.lower()

        # Pick feeds relevant to the query topics
        relevant_feed_names: set[str] = set()
        for topic_key, feed_names in _TOPIC_FEEDS.items():
            if topic_key in query_lower:
                relevant_feed_names.update(feed_names)

        if not relevant_feed_names:
            relevant_feed_names = set(list(_FEEDS.keys())[:5])

        feeds_to_fetch = {name: url for name, url in _FEEDS.items() if name in relevant_feed_names}

        articles = await self._fetch_many(feeds_to_fetch, params.limit * 3)

        # Filter by query terms
        query_words = set(query_lower.split())
        filtered = [
            a for a in articles
            if any(w in (a.title or "").lower() or w in (a.description or "").lower() for w in query_words)
        ]

        return filtered[: params.limit] if filtered else articles[: params.limit]

    async def get_digest_feeds(self, topics: list[str], limit: int = 50) -> list[NewsArticle]:
        """Fetch articles for multiple topics for the weekly digest."""
        relevant_feed_names: set[str] = set()
        for topic in topics:
            topic_lower = topic.lower()
            for topic_key, feed_names in _TOPIC_FEEDS.items():
                if topic_key in topic_lower or topic_lower in topic_key:
                    relevant_feed_names.update(feed_names)

        if not relevant_feed_names:
            relevant_feed_names = set(_FEEDS.keys())

        feeds_to_fetch = {name: url for name, url in _FEEDS.items() if name in relevant_feed_names}
        return await self._fetch_many(feeds_to_fetch, limit)

    async def _fetch_many(self, feeds: dict[str, str], limit: int) -> list[NewsArticle]:
        sem = asyncio.Semaphore(self._max_concurrent)

        async def fetch_one(name: str, url: str) -> list[NewsArticle]:
            async with sem:
                return await self._fetch_feed(name, url)

        results = await asyncio.gather(
            *[fetch_one(name, url) for name, url in feeds.items()],
            return_exceptions=True,
        )

        # Cap each feed's contribution so high-volume feeds (e.g. HackerNews)
        # don't crowd out topic-specific feeds.
        num_feeds = max(len(feeds), 1)
        per_feed = max(5, (limit + num_feeds - 1) // num_feeds)
        articles: list[NewsArticle] = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result[:per_feed])
        return articles[:limit]

    async def _fetch_feed(self, source_name: str, url: str) -> list[NewsArticle]:
        try:
            resp = await self._get_http().get(url)
            resp.raise_for_status()
            content = resp.text
        except Exception as exc:
            logger.debug("rss_client.fetch_failed", source=source_name, url=url, error=str(exc))
            return []

        return _parse_feed(content, source_name)


def _parse_feed(content: str, source_name: str) -> list[NewsArticle]:
    try:
        import feedparser  # type: ignore[import]
    except ImportError:
        logger.warning("rss_client.feedparser_missing", hint="pip install feedparser")
        return []

    try:
        parsed = feedparser.parse(content)
    except Exception as exc:
        logger.debug("rss_client.parse_failed", source=source_name, error=str(exc))
        return []

    articles: list[NewsArticle] = []
    for entry in parsed.get("entries", []):
        article = _parse_entry(entry, source_name)
        if article:
            articles.append(article)

    return articles


def _parse_entry(entry: Any, source_name: str) -> NewsArticle | None:
    title = str(getattr(entry, "title", "") or "").strip()
    link = str(getattr(entry, "link", "") or "").strip()
    if not title or not link:
        return None

    article_id = hashlib.sha256(link.encode()).hexdigest()[:16]

    summary = str(getattr(entry, "summary", "") or "")
    if len(summary) > 500:
        summary = summary[:500]

    published_parsed = getattr(entry, "published_parsed", None)
    published_at: str | None = None
    if published_parsed:
        try:
            import email.utils
            published_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", published_parsed)
        except Exception:
            pass

    author = str(getattr(entry, "author", "") or "").strip() or None

    return NewsArticle(
        id=article_id,
        title=title,
        description=summary or None,
        url=link,
        source_name=source_name,
        news_source=NewsSource.RSS,
        published_at=published_at,
        author=author,
    )
