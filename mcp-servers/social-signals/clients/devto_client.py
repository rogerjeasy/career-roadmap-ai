"""Dev.to client using the public Dev.to API.

No API key required for read-only access. Optional api_key increases rate limits.
Endpoints:
  GET https://dev.to/api/articles?tag=<tag>&top=<days>&per_page=<n>

Rate limits: ~10 req/second unauthenticated, ~10 req/second with key (same limit
but authenticated users get separate quota). The API key allows more robust access.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from clients.base_client import BaseSocialClient
from models import SocialSignal, SocialSource

logger = structlog.get_logger(__name__)

_DEVTO_BASE = "https://dev.to/api"

# Stack → Dev.to tag mapping (Dev.to tags are lowercase, no spaces)
_STACK_TAGS: dict[str, list[str]] = {
    "python": ["python", "django", "fastapi"],
    "javascript": ["javascript", "nodejs", "webdev"],
    "typescript": ["typescript", "javascript"],
    "react": ["react", "javascript", "frontend"],
    "vue": ["vue", "javascript"],
    "angular": ["angular", "javascript"],
    "nextjs": ["nextjs", "react"],
    "node": ["node", "javascript"],
    "fastapi": ["fastapi", "python"],
    "django": ["django", "python"],
    "rust": ["rust"],
    "go": ["go", "golang"],
    "java": ["java", "spring"],
    "kotlin": ["kotlin", "android"],
    "swift": ["swift", "ios"],
    "c#": ["csharp", "dotnet"],
    "dotnet": ["dotnet", "csharp"],
    "docker": ["docker", "devops"],
    "kubernetes": ["kubernetes", "devops"],
    "devops": ["devops", "cicd"],
    "aws": ["aws", "cloud"],
    "gcp": ["googlecloud", "cloud"],
    "azure": ["azure", "cloud"],
    "terraform": ["terraform", "devops"],
    "machine learning": ["machinelearning", "ai"],
    "deep learning": ["deeplearning", "ai"],
    "llm": ["llm", "ai", "machinelearning"],
    "langchain": ["langchain", "ai"],
    "data science": ["datascience", "python"],
    "data engineering": ["dataengineering", "python"],
    "sql": ["sql", "database"],
    "postgresql": ["postgresql", "database"],
    "mongodb": ["mongodb", "database"],
    "graphql": ["graphql", "api"],
    "linux": ["linux", "bash"],
    "security": ["security", "cybersecurity"],
    "flutter": ["flutter", "dart"],
    "react native": ["reactnative", "mobile"],
}

_DEFAULT_TAGS = ["programming", "webdev"]


def _tags_for_stacks(stacks: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for stack in stacks:
        key = stack.lower()
        tags = _STACK_TAGS.get(key, [key.replace(" ", "")])
        for tag in tags[:2]:
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result or _DEFAULT_TAGS[:2]


class DevToClient(BaseSocialClient):
    source = SocialSource.DEVTO

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._api_key = api_key

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "CareerRoadmapAI/1.0",
        }
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    async def _search(
        self,
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        top_days: int = 7,
        **_: Any,
    ) -> list[SocialSignal]:
        tags_to_query = _tags_for_stacks(stacks)

        seen_ids: set[str] = set()
        signals: list[SocialSignal] = []
        per_tag = max(1, limit // len(tags_to_query)) + 2

        for tag in tags_to_query:
            params: dict[str, Any] = {
                "tag": tag,
                "top": top_days,
                "per_page": min(per_tag, 30),
            }

            try:
                resp = await self._get(f"{_DEVTO_BASE}/articles", params=params)
                articles = resp.json()
            except Exception as exc:
                logger.warning(
                    "devto.fetch_error",
                    tag=tag,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                continue

            if not isinstance(articles, list):
                continue

            for article in articles:
                article_id = str(article.get("id", ""))
                if not article_id or article_id in seen_ids:
                    continue
                seen_ids.add(article_id)

                title = str(article.get("title") or "")
                if not title:
                    continue

                url = str(article.get("url") or f"https://dev.to/articles/{article_id}")
                published_at: datetime | None = None
                pub_str = article.get("published_at")
                if pub_str:
                    try:
                        published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass

                tag_list = [str(t) for t in (article.get("tag_list") or []) if t]
                author_data = article.get("user") or {}
                author = str(author_data.get("username") or "")
                score = int(article.get("positive_reactions_count") or 0)
                comment_count = int(article.get("comments_count") or 0)
                summary = str(article.get("description") or "")[:300]

                signals.append(
                    SocialSignal(
                        id=f"devto_{article_id}",
                        title=title,
                        url=url,
                        source=SocialSource.DEVTO,
                        score=score,
                        comment_count=comment_count,
                        author=author,
                        published_at=published_at,
                        tags=tag_list,
                        tech_stack=stacks,
                        summary=summary,
                    )
                )

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals[:limit]
