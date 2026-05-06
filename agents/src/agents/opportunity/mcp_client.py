"""Job-board MCP client for the OpportunityAgent.

Wraps async HTTP calls to the job-board MCP server. The Protocol interface
allows tests to inject a mock without touching network or Redis.
"""
from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

import httpx

from agents.core.logging import get_logger
from agents.opportunity.models import JobListing

logger = get_logger(__name__)

_DEFAULT_JOB_BOARD_URL = "http://localhost:8010"
_DEFAULT_LIMIT = 50
_DEFAULT_TIMEOUT = 20.0


@runtime_checkable
class JobBoardClientProtocol(Protocol):
    async def search_jobs(
        self,
        *,
        role: str,
        location: str | None = None,
        skills: list[str] | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[JobListing]: ...


class JobBoardMCPClient:
    """Async HTTP client for the job-board MCP server."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("JOB_BOARD_MCP_URL", _DEFAULT_JOB_BOARD_URL)).rstrip("/")
        self._api_token = api_token or os.getenv("MCP_API_TOKEN", "")
        self._http_client = http_client

    async def search_jobs(
        self,
        *,
        role: str,
        location: str | None = None,
        skills: list[str] | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[JobListing]:
        """Fetch job listings from the job-board MCP server."""
        params: dict[str, Any] = {"role": role, "limit": limit}
        if location:
            params["location"] = location
        if skills:
            params["skills"] = ",".join(skills[:20])

        headers: dict[str, str] = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        owned_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        try:
            response = await client.get(
                f"{self._base_url}/tools/search_jobs",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            raw_listings: list[dict[str, Any]] = response.json().get("listings", [])
            return [_parse_listing(r) for r in raw_listings]
        except Exception as exc:
            logger.warning(
                "opportunity.mcp.job_fetch_failed",
                role=role,
                error=str(exc),
            )
            raise
        finally:
            if owned_client:
                await client.aclose()


def _parse_listing(raw: dict[str, Any]) -> JobListing:
    salary = raw.get("salary_range") or {}
    return JobListing(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        company=str(raw.get("company", "")),
        location=str(raw.get("location", "")),
        description=str(raw.get("description", "")),
        required_skills=list(raw.get("required_skills", [])),
        salary_min=salary.get("min") if isinstance(salary, dict) else None,
        salary_max=salary.get("max") if isinstance(salary, dict) else None,
        posted_at=str(raw.get("posted_at", "")),
        url=str(raw.get("url", "")),
        remote=bool(raw.get("remote", False)),
        seniority_level=raw.get("seniority_level"),
    )
