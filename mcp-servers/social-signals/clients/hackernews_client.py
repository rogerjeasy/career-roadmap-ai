"""HackerNews client using the Algolia HN Search API.

No API key required. Endpoint:
  GET https://hn.algolia.com/api/v1/search
    ?query=<query>
    &tags=story
    &numericFilters=points>=<min_score>
    &hitsPerPage=<limit>

Rate limits: ~10 000 req/hour (generous, unauthenticated).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from clients.base_client import BaseSocialClient
from models import SocialSignal, SocialSource

logger = structlog.get_logger(__name__)

_HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsClient(BaseSocialClient):
    source = SocialSource.HACKERNEWS

    def __init__(
        self,
        *,
        min_score: int = 10,
        base_url: str = _HN_SEARCH_URL,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._min_score = min_score
        self._base_url = base_url

    async def _search(
        self,
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        tags: list[str] | None = None,
        **_: Any,
    ) -> list[SocialSignal]:
        hn_tags = ",".join(tags) if tags else "story"
        numeric_filter = f"points>={self._min_score}" if self._min_score > 0 else ""

        # Fetch per stack keyword, deduplicate by objectID
        seen_ids: set[str] = set()
        signals: list[SocialSignal] = []

        per_stack = max(1, limit // len(stacks)) + 2  # slight over-fetch

        for stack in stacks:
            params: dict[str, Any] = {
                "query": stack,
                "tags": hn_tags,
                "hitsPerPage": min(per_stack, 30),
            }
            if numeric_filter:
                params["numericFilters"] = numeric_filter

            try:
                resp = await self._get(self._base_url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "hackernews.fetch_error",
                    stack=stack,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                continue

            for hit in data.get("hits", []):
                obj_id = str(hit.get("objectID", ""))
                if not obj_id or obj_id in seen_ids:
                    continue
                seen_ids.add(obj_id)

                published_at: datetime | None = None
                created_str = hit.get("created_at")
                if created_str:
                    try:
                        published_at = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                url = hit.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
                title = hit.get("title") or hit.get("story_title") or ""
                if not title:
                    continue

                signals.append(
                    SocialSignal(
                        id=f"hn_{obj_id}",
                        title=title,
                        url=url,
                        source=SocialSource.HACKERNEWS,
                        score=int(hit.get("points") or 0),
                        comment_count=int(hit.get("num_comments") or 0),
                        author=str(hit.get("author") or ""),
                        published_at=published_at,
                        tags=[
                            t
                            for t in (hit.get("_tags") or [])
                            if not t.startswith("author_") and not t.startswith("story_")
                        ],
                        tech_stack=[stack],
                        summary="",
                    )
                )

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals[:limit]
