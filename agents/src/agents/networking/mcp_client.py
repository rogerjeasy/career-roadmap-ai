"""MCP client abstraction for the Networking agent (LinkedIn Profile + Industry News servers).

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
    """Structural interface for MCP calls.

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
      {
        "linkedin_profile": "http://mcp-linkedin-profile:3004",
        "industry_news":    "http://mcp-industry-news:3007",
      }

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
                "mcp_net.call_failed",
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
            "mcp_net.call_ok",
            server_id=server_id,
            tool=tool,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
        )
        return body.get("result", {})


class StubMCPClient:
    """Realistic stub MCP client for tests and unconfigured environments.

    Returns plausible networking data without any network calls.
    Inject a custom ``StubMCPClient`` in tests to control returned data precisely.
    """

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        if server_id == "linkedin_profile" and tool == "profile.fetch":
            return _stub_linkedin_profile(params)
        if server_id == "industry_news" and tool == "events.search":
            return _stub_events_search(params)
        return {"results": [], "total_count": 0, "fetched_at": datetime.now(UTC).isoformat()}


# ── Stub data helpers ─────────────────────────────────────────────────────────


def _stub_linkedin_profile(params: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic stub LinkedIn profile for testing."""
    return {
        "headline": "Software Engineer | Python · FastAPI · Docker | Seeking AI/ML Roles",
        "summary": (
            "Backend engineer with 4 years building scalable Python APIs and microservices. "
            "Now actively expanding into ML engineering — completed Andrew Ng's ML course and "
            "building a personal RAG project. Passionate about bridging software engineering "
            "practices and applied AI."
        ),
        "experience": [
            {
                "title": "Backend Engineer",
                "company": "TechCorp AG",
                "duration_months": 36,
                "description": "Built FastAPI microservices serving 10k RPS. Led migration to async Python.",
            },
            {
                "title": "Junior Software Developer",
                "company": "StartupX",
                "duration_months": 18,
                "description": "Python, Django, PostgreSQL web development for SaaS platform.",
            },
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "SQL", "REST APIs"],
        "education": [
            {"degree": "BSc Computer Science", "institution": "EPFL", "year": 2020}
        ],
        "connections": 342,
        "profile_completeness": 0.72,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


# ── Events stub catalog ───────────────────────────────────────────────────────

_EVENTS_BY_TOPIC: dict[str, list[dict[str, Any]]] = {
    "machine learning": [
        {
            "id": "evt-ml-001",
            "title": "ML Summit Zurich 2026",
            "type": "conference",
            "platform": "Eventbrite",
            "skill_tags": ["machine learning", "deep learning", "mlops"],
            "description": "Annual ML conference featuring speakers from Google, ETH Zurich, and leading startups.",
            "url": "https://mlsummit.ch",
            "date": "2026-09-15",
            "location": "Zurich, Switzerland",
            "is_online": False,
        },
        {
            "id": "evt-ml-002",
            "title": "Machine Learning Zurich Meetup",
            "type": "meetup",
            "platform": "Meetup.com",
            "skill_tags": ["machine learning", "python", "data science"],
            "description": "Monthly meetup for ML practitioners in Zurich. Lightning talks + networking.",
            "url": "https://meetup.com/machine-learning-zurich",
            "date": None,
            "location": "Zurich, Switzerland",
            "is_online": False,
        },
        {
            "id": "evt-ml-003",
            "title": "Hugging Face Community Discord",
            "type": "online_community",
            "platform": "Discord",
            "skill_tags": ["transformers", "nlp", "machine learning", "hugging face"],
            "description": "130k+ member Discord for ML engineers using Hugging Face transformers.",
            "url": "https://discord.gg/hugging-face",
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": "evt-ml-004",
            "title": "r/MachineLearning",
            "type": "forum",
            "platform": "Reddit",
            "skill_tags": ["machine learning", "research", "papers"],
            "description": "Top ML research discussion forum with 3M+ members.",
            "url": "https://reddit.com/r/machinelearning",
            "date": None,
            "location": None,
            "is_online": True,
        },
    ],
    "python": [
        {
            "id": "evt-py-001",
            "title": "EuroPython 2026",
            "type": "conference",
            "platform": "Eventbrite",
            "skill_tags": ["python", "fastapi", "async", "data"],
            "description": "Europe's largest Python conference. 3-day event with 1,500+ attendees.",
            "url": "https://europython.eu",
            "date": "2026-07-14",
            "location": "Prague, Czech Republic",
            "is_online": False,
        },
        {
            "id": "evt-py-002",
            "title": "Python Discord Server",
            "type": "online_community",
            "platform": "Discord",
            "skill_tags": ["python", "programming", "beginners"],
            "description": "270,000+ Python developers. Great for networking and code review.",
            "url": "https://discord.gg/python",
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": "evt-py-003",
            "title": "PyData Newsletter",
            "type": "newsletter",
            "platform": "Substack",
            "skill_tags": ["python", "data science", "pandas", "numpy"],
            "description": "Weekly Python data science news and tutorials. 80k+ subscribers.",
            "url": "https://pydata.org",
            "date": None,
            "location": None,
            "is_online": True,
        },
    ],
    "ai": [
        {
            "id": "evt-ai-001",
            "title": "AI & Society Forum Geneva",
            "type": "conference",
            "platform": "LinkedIn Events",
            "skill_tags": ["ai", "ethics", "machine learning", "policy"],
            "description": "Annual forum at the intersection of AI technology and societal impact.",
            "url": None,
            "date": "2026-11-20",
            "location": "Geneva, Switzerland",
            "is_online": False,
        },
        {
            "id": "evt-ai-002",
            "title": "LLM Engineers Newsletter",
            "type": "newsletter",
            "platform": "Substack",
            "skill_tags": ["llm", "ai engineering", "langchain", "rag"],
            "description": "Weekly newsletter on LLM engineering from practitioners. 50k+ subscribers.",
            "url": "https://llmengineer.substack.com",
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": "evt-ai-003",
            "title": "AI/ML Practitioners Slack",
            "type": "online_community",
            "platform": "Slack",
            "skill_tags": ["ai", "machine learning", "llm", "mlops"],
            "description": "25,000 AI/ML practitioners sharing jobs, papers, and tools.",
            "url": None,
            "date": None,
            "location": None,
            "is_online": True,
        },
    ],
    "software engineering": [
        {
            "id": "evt-se-001",
            "title": "QCon Zurich",
            "type": "conference",
            "platform": "InfoQ",
            "skill_tags": ["software architecture", "microservices", "devops"],
            "description": "Enterprise software development conference focused on architecture patterns.",
            "url": "https://qconzurich.com",
            "date": "2026-06-12",
            "location": "Zurich, Switzerland",
            "is_online": False,
        },
        {
            "id": "evt-se-002",
            "title": "Software Engineering Daily Podcast",
            "type": "newsletter",
            "platform": "Podcast",
            "skill_tags": ["software engineering", "architecture", "distributed systems"],
            "description": "Daily interviews with top engineers. Great for staying current on trends.",
            "url": "https://softwareengineeringdaily.com",
            "date": None,
            "location": None,
            "is_online": True,
        },
    ],
    "mlops": [
        {
            "id": "evt-mlo-001",
            "title": "MLOps Community",
            "type": "online_community",
            "platform": "Slack",
            "skill_tags": ["mlops", "model deployment", "monitoring", "feature store"],
            "description": "20,000+ MLOps practitioners. Weekly AMAs with industry experts.",
            "url": "https://mlops.community",
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": "evt-mlo-002",
            "title": "MLOps World Summit",
            "type": "conference",
            "platform": "Eventbrite",
            "skill_tags": ["mlops", "feature engineering", "ci/cd", "model registry"],
            "description": "Two-day summit covering end-to-end ML production engineering.",
            "url": "https://mlopsworld.com",
            "date": "2026-10-08",
            "location": "Toronto / Online",
            "is_online": True,
        },
    ],
    "data engineering": [
        {
            "id": "evt-de-001",
            "title": "Data Engineering Weekly",
            "type": "newsletter",
            "platform": "Substack",
            "skill_tags": ["data engineering", "spark", "airflow", "dbt"],
            "description": "Weekly newsletter covering the modern data stack. 40k+ subscribers.",
            "url": "https://dataengineeringweekly.com",
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": "evt-de-002",
            "title": "Data Engineering Zoomcamp",
            "type": "webinar",
            "platform": "DataTalks.Club",
            "skill_tags": ["data engineering", "bigquery", "dbt", "kafka", "spark"],
            "description": "Free 9-week data engineering course with weekly live sessions.",
            "url": "https://github.com/DataTalksClub/data-engineering-zoomcamp",
            "date": None,
            "location": None,
            "is_online": True,
        },
    ],
}


def _stub_events_search(params: dict[str, Any]) -> dict[str, Any]:
    """Return stub events matching the requested topic."""
    topic_raw = str(params.get("topic", "")).lower().strip()
    limit = int(params.get("limit", 6))

    events = _EVENTS_BY_TOPIC.get(topic_raw, [])

    if not events:
        for key, key_events in _EVENTS_BY_TOPIC.items():
            if topic_raw in key or key in topic_raw:
                events = key_events
                break

    if not events:
        events = _generic_events(topic_raw)

    return {
        "events": events[:limit],
        "total_count": len(events),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _generic_events(topic: str) -> list[dict[str, Any]]:
    """Generate generic stub events for topics not in the catalog."""
    title_cased = topic.title()
    return [
        {
            "id": f"gen-evt-{topic[:8]}-001",
            "title": f"{title_cased} Practitioners Meetup",
            "type": "meetup",
            "platform": "Meetup.com",
            "skill_tags": [topic],
            "description": f"Monthly meetup for {title_cased} practitioners. Network and learn.",
            "url": None,
            "date": None,
            "location": None,
            "is_online": True,
        },
        {
            "id": f"gen-evt-{topic[:8]}-002",
            "title": f"{title_cased} Community Slack",
            "type": "online_community",
            "platform": "Slack",
            "skill_tags": [topic],
            "description": f"Active Slack workspace for {title_cased} engineers and practitioners.",
            "url": None,
            "date": None,
            "location": None,
            "is_online": True,
        },
    ]
