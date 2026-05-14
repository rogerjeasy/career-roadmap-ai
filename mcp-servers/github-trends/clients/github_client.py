"""GitHub REST API client with circuit breaker.

Uses the official GitHub REST API v3 (search endpoints).
Unauthenticated: 60 req/hr. With GITHUB_TOKEN: 5000 req/hr.

Reference: https://docs.github.com/en/rest/search/search
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from models import (
    GetGoodFirstIssuesParams,
    GetTrendingReposParams,
    GoodFirstIssue,
    TrendingRepo,
)
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger(__name__)

_LANGUAGE_TOPICS: dict[str, list[str]] = {
    "python": ["machine-learning", "deep-learning", "pytorch", "transformers", "fastapi"],
    "javascript": ["react", "nextjs", "typescript", "nodejs"],
    "typescript": ["react", "nextjs", "nest", "angular"],
    "rust": ["webassembly", "systems", "async"],
    "go": ["cloud-native", "kubernetes", "grpc"],
    "java": ["spring", "microservices", "kafka"],
}


class GitHubClient:
    """GitHub REST API v3 client with optional token auth and circuit breaker."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            "github_trends.github_api",
            failure_threshold=5,
            reset_timeout_s=60.0,
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CareerRoadmapAI/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._headers(),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        resp = await self._get_client().get(f"{self._base_url}{path}", params=params)
        resp.raise_for_status()
        return resp

    async def get_trending_repos(self, params: GetTrendingReposParams) -> list[TrendingRepo]:
        """Search for trending repos by approximating 'created/pushed recently + high stars'."""
        since_date = (datetime.now(timezone.utc) - timedelta(days=params.since_days)).strftime(
            "%Y-%m-%d"
        )

        query_parts = [
            f"language:{params.language}",
            f"pushed:>{since_date}",
            f"stars:>{params.min_stars}",
        ]
        if params.topic:
            query_parts.append(f"topic:{params.topic}")

        query = " ".join(query_parts)

        async def _fetch() -> list[TrendingRepo]:
            try:
                resp = await self._get(
                    "/search/repositories",
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": min(params.limit, 30),
                    },
                )
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    logger.warning("github_client.rate_limited", path="/search/repositories")
                    return []
                raise

            repos: list[TrendingRepo] = []
            for item in data.get("items", []):
                repo = _parse_repo(item)
                if repo:
                    repos.append(repo)
                if len(repos) >= params.limit:
                    break
            return repos

        try:
            return await self._breaker.call(_fetch())
        except CircuitOpenError:
            logger.warning("github_client.circuit_open", endpoint="/search/repositories")
            return []
        except Exception as exc:
            logger.warning("github_client.trending_repos_failed", error=str(exc))
            return []

    async def get_good_first_issues(self, params: GetGoodFirstIssuesParams) -> list[GoodFirstIssue]:
        """Search for open issues labelled 'good first issue' in the given language."""
        query_parts = [
            'label:"good first issue"',
            "state:open",
            "is:issue",
            f"language:{params.language}",
        ]
        if params.topic:
            query_parts.append(f"topic:{params.topic}")
        if params.max_comments > 0:
            query_parts.append(f"comments:<={params.max_comments}")

        query = " ".join(query_parts)

        async def _fetch() -> list[GoodFirstIssue]:
            try:
                resp = await self._get(
                    "/search/issues",
                    params={
                        "q": query,
                        "sort": "created",
                        "order": "desc",
                        "per_page": min(params.limit, 30),
                    },
                )
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    logger.warning("github_client.rate_limited", path="/search/issues")
                    return []
                raise

            issues: list[GoodFirstIssue] = []
            for item in data.get("items", []):
                issue = _parse_issue(item, params.language)
                if issue:
                    issues.append(issue)
                if len(issues) >= params.limit:
                    break
            return issues

        try:
            return await self._breaker.call(_fetch())
        except CircuitOpenError:
            logger.warning("github_client.circuit_open", endpoint="/search/issues")
            return []
        except Exception as exc:
            logger.warning("github_client.good_first_issues_failed", error=str(exc))
            return []


def _parse_repo(item: dict[str, Any]) -> TrendingRepo | None:
    try:
        return TrendingRepo(
            id=item["id"],
            name=item["name"],
            full_name=item["full_name"],
            description=item.get("description"),
            url=item["html_url"],
            stars=item.get("stargazers_count", 0),
            forks=item.get("forks_count", 0),
            open_issues=item.get("open_issues_count", 0),
            language=item.get("language"),
            topics=item.get("topics", []),
            created_at=item.get("created_at"),
            pushed_at=item.get("pushed_at"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("github_client.parse_repo_failed", error=str(exc))
        return None


def _parse_issue(item: dict[str, Any], language: str) -> GoodFirstIssue | None:
    try:
        repo_url_parts = item.get("repository_url", "").split("/")
        repo_full_name = "/".join(repo_url_parts[-2:]) if len(repo_url_parts) >= 2 else ""

        labels = [label["name"] for label in item.get("labels", []) if isinstance(label, dict)]
        return GoodFirstIssue(
            id=item["id"],
            number=item["number"],
            title=item["title"],
            url=item["html_url"],
            repo_full_name=repo_full_name,
            repo_url=f"https://github.com/{repo_full_name}",
            language=language,
            labels=labels,
            comments=item.get("comments", 0),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("github_client.parse_issue_failed", error=str(exc))
        return None
