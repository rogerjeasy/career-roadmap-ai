"""Twitter/X client using the Twitter API v2 recent search endpoint.

Requires a Bearer Token (OAuth 2.0 App-Only).
Endpoint:
  GET https://api.twitter.com/2/tweets/search/recent
    ?query=<query>
    &max_results=<n>
    &tweet.fields=public_metrics,created_at,entities
    &expansions=author_id
    &user.fields=username

Skipped gracefully when TWITTER_BEARER_TOKEN is not set.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from clients.base_client import BaseSocialClient
from models import SocialSignal, SocialSource

logger = structlog.get_logger(__name__)

_TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterClient(BaseSocialClient):
    source = SocialSource.TWITTER

    def __init__(
        self,
        bearer_token: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._bearer_token = bearer_token

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
        }

    async def _search(
        self,
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        **_: Any,
    ) -> list[SocialSignal]:
        # Build OR query excluding retweets, in English
        stack_terms = " OR ".join(f'"{s}"' if " " in s else s for s in stacks)
        query = f"({stack_terms}) -is:retweet lang:en"

        # Twitter API v2 minimum is 10 results
        max_results = max(10, min(limit, 100))

        params: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "tweet.fields": "public_metrics,created_at,entities",
            "expansions": "author_id",
            "user.fields": "username",
        }

        try:
            resp = await self._get(_TWITTER_SEARCH_URL, params=params)
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning(
                    "twitter.rate_limited",
                    correlation_id=correlation_id,
                )
            raise

        tweets = data.get("data") or []
        users: dict[str, str] = {}
        for u in (data.get("includes") or {}).get("users") or []:
            users[u["id"]] = u.get("username", "")

        signals: list[SocialSignal] = []
        for tweet in tweets[:limit]:
            tweet_id = str(tweet.get("id", ""))
            if not tweet_id:
                continue

            metrics = tweet.get("public_metrics") or {}
            score = int(metrics.get("like_count") or 0) + int(metrics.get("retweet_count") or 0)
            comment_count = int(metrics.get("reply_count") or 0)

            author_id = str(tweet.get("author_id") or "")
            author = users.get(author_id, "")

            published_at: datetime | None = None
            created_at = tweet.get("created_at")
            if created_at:
                try:
                    published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Extract hashtags as tags
            entities = tweet.get("entities") or {}
            hashtags = [
                h.get("tag", "") for h in (entities.get("hashtags") or []) if h.get("tag")
            ]

            text = str(tweet.get("text") or "")
            tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"

            signals.append(
                SocialSignal(
                    id=f"twitter_{tweet_id}",
                    title=text[:140],
                    url=tweet_url,
                    source=SocialSource.TWITTER,
                    score=score,
                    comment_count=comment_count,
                    author=author,
                    published_at=published_at,
                    tags=hashtags[:10],
                    tech_stack=stacks,
                    summary=text[:300],
                )
            )

        return signals
