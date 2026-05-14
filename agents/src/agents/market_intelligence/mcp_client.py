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
            from opentelemetry import propagate as otel_propagate

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "X-Correlation-ID": correlation_id,
            }
            # Inject W3C traceparent/tracestate so the MCP server continues the trace
            otel_propagate.inject(headers)

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    base_url,
                    json=request_body,
                    headers=headers,
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
        "ranges": [
            {
                "role": role,
                "country": country,
                "currency": currency,
                "experience_level": "mid",
                "p25": int(base * 0.80),
                "median": base,
                "p75": int(base * 1.25),
                "sample_count": 12,
                "sources": ["Levels.fyi", "Glassdoor"],
                "fetched_at": datetime.now(UTC).date().isoformat(),
            }
        ],
        "role": role,
        "country": country,
        "total_sources": 2,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _stub_github_trends() -> dict[str, Any]:
    return {
        "repos": [
            {"name": "langchain-ai/langchain", "description": "LLM framework", "stars": 4200, "language": "Python", "url": "https://github.com/langchain-ai/langchain"},
            {"name": "microsoft/autogen", "description": "Multi-agent AI", "stars": 3100, "language": "Python", "url": "https://github.com/microsoft/autogen"},
            {"name": "tiangolo/fastapi", "description": "FastAPI framework", "stars": 2800, "language": "Python", "url": "https://github.com/tiangolo/fastapi"},
            {"name": "kubernetes/kubernetes", "description": "Container orchestration", "stars": 1900, "language": "Go", "url": "https://github.com/kubernetes/kubernetes"},
            {"name": "hashicorp/terraform", "description": "IaC tool", "stars": 1700, "language": "HCL", "url": "https://github.com/hashicorp/terraform"},
        ],
        "total_count": 5,
        "language": "python",
        "since_days": 7,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _stub_social_signals() -> dict[str, Any]:
    return {
        "topics": [
            {"name": "AI agents", "score": 450, "signal_count": 8, "sources": ["hackernews", "reddit"], "category": "artificial intelligence"},
            {"name": "LLMs", "score": 380, "signal_count": 6, "sources": ["hackernews", "reddit"], "category": "machine learning"},
            {"name": "Kubernetes", "score": 320, "signal_count": 5, "sources": ["hackernews"], "category": "devops"},
            {"name": "FastAPI", "score": 280, "signal_count": 4, "sources": ["reddit"], "category": "python"},
        ],
        "total_signals_analysed": 24,
        "stacks_queried": ["python", "fastapi"],
        "sources_queried": ["hackernews", "reddit"],
        "fetched_at": datetime.now(UTC).isoformat(),
    }
