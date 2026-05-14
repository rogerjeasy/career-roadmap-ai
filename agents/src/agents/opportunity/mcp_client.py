"""Job-board MCP client for the OpportunityAgent.

Wraps async HTTP calls to the job-board MCP server (JSON-RPC 2.0 over POST /).
The Protocol interface allows tests to inject a mock without touching network or Redis.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

import httpx
from opentelemetry import propagate as otel_propagate

from agents.config import agent_settings
from agents.core.gateway_metrics import mcp_tool_calls_total
from agents.core.logging import get_logger
from agents.opportunity.models import JobListing

logger = get_logger(__name__)

_DEFAULT_JOB_BOARD_URL = "http://localhost:3001"
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
        self._base_url = (base_url or agent_settings.mcp_job_board_url or _DEFAULT_JOB_BOARD_URL).rstrip("/")
        self._api_token = api_token or agent_settings.mcp_api_token
        self._http_client = http_client

    async def search_jobs(
        self,
        *,
        role: str,
        location: str | None = None,
        skills: list[str] | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[JobListing]:
        """Fetch job listings from the job-board MCP server via JSON-RPC 2.0."""
        params: dict[str, Any] = {"role": role, "limit": limit}
        if location:
            params["location"] = location
        if skills:
            params["skills"] = skills[:20]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_token:
            headers["X-MCP-API-Key"] = self._api_token
        otel_propagate.inject(headers)  # propagate W3C traceparent to MCP server

        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "search_jobs",
            "params": params,
        }

        owned_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        try:
            response = await client.post(
                f"{self._base_url}/",
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"MCP error {payload['error'].get('code')}: {payload['error'].get('message')}")
            raw_listings: list[dict[str, Any]] = payload.get("result", {}).get("postings", [])
            mcp_tool_calls_total.labels(server="job_board", tool="search_jobs", outcome="success").inc()
            return [_parse_listing(r) for r in raw_listings]
        except Exception as exc:
            mcp_tool_calls_total.labels(server="job_board", tool="search_jobs", outcome="error").inc()
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
    return JobListing(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        company=str(raw.get("company", "")),
        location=str(raw.get("location", "")),
        description=str(raw.get("description", "")),
        required_skills=list(raw.get("required_skills", [])),
        salary_min=raw.get("salary_min"),
        salary_max=raw.get("salary_max"),
        posted_at=str(raw.get("posted_date", "")),
        url=str(raw.get("url", "")),
        remote=bool(raw.get("remote", False)),
        seniority_level=raw.get("seniority_level"),
    )
