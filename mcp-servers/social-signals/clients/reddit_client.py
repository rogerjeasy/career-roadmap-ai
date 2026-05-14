"""Reddit client using the public JSON API.

No OAuth required for read-only access. Endpoint:
  GET https://www.reddit.com/r/<subreddit>/search.json
    ?q=<query>&sort=top&t=week&limit=<n>&restrict_sr=true

Rate limits: ~60 req/min unauthenticated (enforced via User-Agent).
Reddit requires a descriptive User-Agent or requests are throttled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from clients.base_client import BaseSocialClient
from models import SocialSignal, SocialSource

logger = structlog.get_logger(__name__)

_REDDIT_BASE = "https://www.reddit.com"

# Stack → primary subreddit mapping (covers most career-relevant stacks)
_STACK_SUBREDDITS: dict[str, list[str]] = {
    "python": ["Python", "learnpython", "django", "flask"],
    "javascript": ["javascript", "webdev", "node"],
    "typescript": ["typescript", "webdev"],
    "react": ["reactjs", "webdev", "Frontend"],
    "vue": ["vuejs", "webdev"],
    "angular": ["angularjs", "webdev"],
    "nextjs": ["nextjs", "webdev"],
    "node": ["node", "javascript", "webdev"],
    "fastapi": ["Python", "FastAPI"],
    "django": ["django", "Python"],
    "flask": ["flask", "Python"],
    "rust": ["rust", "rust_gamedev"],
    "go": ["golang", "golangjob"],
    "java": ["java", "javahelp"],
    "kotlin": ["Kotlin", "androiddev"],
    "swift": ["swift", "iOSProgramming"],
    "c#": ["csharp", "dotnet"],
    "dotnet": ["dotnet", "csharp"],
    "docker": ["docker", "devops"],
    "kubernetes": ["kubernetes", "devops"],
    "devops": ["devops", "sysadmin"],
    "aws": ["aws", "devops", "cloud"],
    "gcp": ["googlecloud", "devops"],
    "azure": ["AZURE", "devops"],
    "terraform": ["Terraform", "devops"],
    "machine learning": ["MachineLearning", "learnmachinelearning"],
    "deep learning": ["deeplearning", "MachineLearning"],
    "llm": ["MachineLearning", "LocalLLaMA", "ChatGPT"],
    "langchain": ["LangChain", "MachineLearning"],
    "data science": ["datascience", "learnpython"],
    "data engineering": ["dataengineering", "datascience"],
    "sql": ["SQL", "dataengineering"],
    "postgresql": ["PostgreSQL", "dataengineering"],
    "mongodb": ["mongodb", "dataengineering"],
    "redis": ["redis", "devops"],
    "graphql": ["graphql", "webdev"],
    "linux": ["linux", "sysadmin"],
    "security": ["netsec", "cybersecurity"],
    "blockchain": ["ethereum", "CryptoTechnology"],
    "flutter": ["FlutterDev", "androiddev"],
    "react native": ["reactnative", "androiddev"],
}

_DEFAULT_SUBREDDITS = ["programming", "learnprogramming", "cscareerquestions"]


def _subreddits_for_stacks(stacks: list[str]) -> list[str]:
    """Return a deduplicated, ordered list of subreddits for the given stacks."""
    seen: set[str] = set()
    result: list[str] = []
    for stack in stacks:
        key = stack.lower()
        subs = _STACK_SUBREDDITS.get(key, _DEFAULT_SUBREDDITS[:1])
        for sub in subs[:2]:  # max 2 subreddits per stack
            if sub.lower() not in seen:
                seen.add(sub.lower())
                result.append(sub)
    return result or _DEFAULT_SUBREDDITS[:2]


class RedditClient(BaseSocialClient):
    source = SocialSource.REDDIT

    def __init__(
        self,
        *,
        user_agent: str = "CareerRoadmapAI/1.0",
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries)
        self._user_agent = user_agent

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }

    async def _search(
        self,
        stacks: list[str],
        limit: int,
        *,
        correlation_id: str = "",
        subreddits: list[str] | None = None,
        time_filter: str = "week",
        sort: str = "top",
        **_: Any,
    ) -> list[SocialSignal]:
        target_subs = subreddits or _subreddits_for_stacks(stacks)
        query = " OR ".join(stacks)

        seen_ids: set[str] = set()
        signals: list[SocialSignal] = []

        for subreddit in target_subs:
            url = f"{_REDDIT_BASE}/r/{subreddit}/search.json"
            params: dict[str, Any] = {
                "q": query,
                "sort": sort,
                "t": time_filter,
                "limit": min(limit, 25),
                "restrict_sr": "true",
            }

            try:
                resp = await self._get(url, params=params)
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "reddit.fetch_error",
                    subreddit=subreddit,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                continue

            children = data.get("data", {}).get("children", [])
            for child in children:
                post = child.get("data", {})
                post_id = str(post.get("id", ""))
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                title = str(post.get("title") or "")
                if not title:
                    continue

                permalink = post.get("permalink", "")
                url_val = post.get("url") or f"{_REDDIT_BASE}{permalink}"
                created_utc = post.get("created_utc")
                published_at: datetime | None = None
                if created_utc:
                    try:
                        published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
                    except (ValueError, OSError):
                        pass

                flair = post.get("link_flair_text") or ""
                tags = [flair] if flair else []

                signals.append(
                    SocialSignal(
                        id=f"reddit_{post_id}",
                        title=title,
                        url=str(url_val),
                        source=SocialSource.REDDIT,
                        score=int(post.get("score") or 0),
                        comment_count=int(post.get("num_comments") or 0),
                        author=str(post.get("author") or ""),
                        published_at=published_at,
                        tags=tags,
                        tech_stack=stacks,
                        summary=str(post.get("selftext") or "")[:300],
                    )
                )

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals[:limit]
