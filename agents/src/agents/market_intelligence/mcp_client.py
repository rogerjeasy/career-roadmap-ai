"""MCP client abstraction for market intelligence tool calls.

Provides:
  MCPClientProtocol  — structural typing interface (Protocol)
  HttpMCPClient      — production JSON-RPC 2.0 over HTTP (requires httpx)
  StubMCPClient      — realistic mock data for tests / unconfigured servers

The agent depends only on MCPClientProtocol; the concrete class is injected
at construction time, keeping the agent fully decoupled from transport.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agents.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class MCPClientProtocol(Protocol):
    """Structural interface for MCP tool server calls.

    Agents depend on this protocol, not a concrete class.
    ``StubMCPClient`` satisfies it without subclassing.
    """

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Call a named tool on a registered MCP server and return the result dict."""
        ...


class HttpMCPClient:
    """Production MCP client using JSON-RPC 2.0 over HTTP.

    Server URLs are passed as a registry dict:
      {"job_board": "http://mcp-job-board:3001", "salary_benchmark": "http://..."}

    Requires ``httpx`` — add to pyproject.toml if absent.
    """

    def __init__(
        self,
        server_registry: dict[str, str],
        timeout_seconds: float = 30.0,
    ) -> None:
        self._registry = server_registry
        self._timeout = timeout_seconds

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        import httpx

        base_url = self._registry.get(server_id)
        if not base_url:
            raise ValueError(f"MCP server '{server_id}' not registered")

        request_body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": tool,
            "params": params,
        }
        t0 = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    base_url,
                    json=request_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Correlation-ID": correlation_id,
                    },
                )
                resp.raise_for_status()
                body: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning(
                "mcp.call_failed",
                server_id=server_id,
                tool=tool,
                error=str(exc),
                correlation_id=correlation_id,
            )
            raise

        if "error" in body:
            err = body["error"]
            raise RuntimeError(
                f"MCP error [{err.get('code', -1)}]: {err.get('message', 'unknown')}"
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "mcp.call_ok",
            server_id=server_id,
            tool=tool,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
        )
        return body.get("result", {})


class StubMCPClient:
    """Realistic stub MCP client for tests and unconfigured environments.

    Returns plausible mock data without any network calls.
    Inject a custom ``StubMCPClient`` in tests to control the returned data precisely.
    """

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        role = str(params.get("role", params.get("target_role", "Software Engineer")))
        country = str(params.get("country", "CH"))

        if server_id == "job_board":
            return _stub_job_board(role, country)
        if server_id == "salary_benchmark":
            return _stub_salary(role, country)
        if server_id == "github_trends":
            return _stub_github_trends()
        if server_id == "social_signals":
            return _stub_social_signals()
        return {}


# ── Stub data helpers ────────────────────────────────────────────────────────

_COUNTRY_CURRENCY: dict[str, str] = {
    "CH": "CHF",
    "DE": "EUR",
    "FR": "EUR",
    "AT": "EUR",
    "NL": "EUR",
    "ES": "EUR",
    "IT": "EUR",
    "US": "USD",
    "UK": "GBP",
    "CA": "CAD",
    "AU": "AUD",
    "SG": "SGD",
}
_COUNTRY_BASE_SALARY: dict[str, int] = {
    "CH": 115_000,
    "DE": 78_000,
    "FR": 67_000,
    "AT": 65_000,
    "NL": 72_000,
    "US": 135_000,
    "UK": 92_000,
    "CA": 105_000,
    "AU": 100_000,
    "SG": 95_000,
}


def _stub_job_board(role: str, country: str) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    currency = _COUNTRY_CURRENCY.get(country, "USD")
    base = _COUNTRY_BASE_SALARY.get(country, 80_000)
    return {
        "postings": [
            {
                "title": role,
                "company": "TechCorp AG",
                "location": f"Zurich, {country}",
                "required_skills": ["Python", "Docker", "Kubernetes", "AWS", "FastAPI"],
                "source": "LinkedIn",
                "posted_date": today,
                "salary_min": int(base * 0.85),
                "salary_max": int(base * 1.15),
                "currency": currency,
                "url": "https://linkedin.com/jobs/stub-1",
            },
            {
                "title": role,
                "company": "DataFlow GmbH",
                "location": f"Basel, {country}",
                "required_skills": [
                    "Python",
                    "Apache Kafka",
                    "Spark",
                    "Kubernetes",
                    "Terraform",
                ],
                "source": "Indeed",
                "posted_date": today,
                "salary_min": int(base * 0.80),
                "salary_max": int(base * 1.10),
                "currency": currency,
                "url": "https://indeed.com/jobs/stub-2",
            },
            {
                "title": role,
                "company": "AI Ventures AG",
                "location": f"Bern, {country}",
                "required_skills": [
                    "Python",
                    "PyTorch",
                    "LangChain",
                    "Kubernetes",
                    "FastAPI",
                ],
                "source": "Glassdoor",
                "posted_date": today,
                "salary_min": int(base * 0.90),
                "salary_max": int(base * 1.20),
                "currency": currency,
                "url": "https://glassdoor.com/jobs/stub-3",
            },
        ],
        "total_count": 127,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _stub_salary(role: str, country: str) -> dict[str, Any]:
    currency = _COUNTRY_CURRENCY.get(country, "USD")
    base = _COUNTRY_BASE_SALARY.get(country, 80_000)
    return {
        "role": role,
        "country": country,
        "median_annual": base,
        "p25_annual": int(base * 0.80),
        "p75_annual": int(base * 1.25),
        "currency": currency,
        "source": "Levels.fyi + Glassdoor",
        "freshness_date": datetime.now(UTC).date().isoformat(),
    }


def _stub_github_trends() -> dict[str, Any]:
    return {
        "trending_repos": [
            {
                "name": "langchain-ai/langchain",
                "topic": "LLM frameworks",
                "stars_this_week": 4200,
                "language": "Python",
            },
            {
                "name": "microsoft/autogen",
                "topic": "Multi-agent AI",
                "stars_this_week": 3100,
                "language": "Python",
            },
            {
                "name": "tiangolo/fastapi",
                "topic": "FastAPI",
                "stars_this_week": 2800,
                "language": "Python",
            },
            {
                "name": "kubernetes/kubernetes",
                "topic": "Kubernetes",
                "stars_this_week": 1900,
                "language": "Go",
            },
            {
                "name": "hashicorp/terraform",
                "topic": "Terraform",
                "stars_this_week": 1700,
                "language": "HCL",
            },
        ],
        "trending_topics": [
            "AI agents",
            "LLMs",
            "Kubernetes",
            "FastAPI",
            "Rust",
            "WebAssembly",
        ],
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _stub_social_signals() -> dict[str, Any]:
    return {
        "hackernews": [
            {
                "title": "Ask HN: What skills matter most for AI engineers in 2026?",
                "points": 450,
                "url": "https://news.ycombinator.com/stub-1",
            },
            {
                "title": "Kubernetes is still the standard for container orchestration",
                "points": 380,
                "url": "https://news.ycombinator.com/stub-2",
            },
        ],
        "reddit": [
            {
                "subreddit": "r/MachineLearning",
                "title": "LLM agent frameworks comparison 2026",
                "upvotes": 2100,
                "url": "https://reddit.com/stub-1",
            },
            {
                "subreddit": "r/Python",
                "title": "FastAPI vs Django for AI services",
                "upvotes": 1850,
                "url": "https://reddit.com/stub-2",
            },
        ],
        "trending_topics": [
            "AI agents",
            "prompt engineering",
            "Rust for AI",
            "serverless ML",
        ],
        "fetched_at": datetime.now(UTC).isoformat(),
    }
