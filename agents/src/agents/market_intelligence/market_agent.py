"""MarketAgent — L3 Specialist Agent: real-time market intelligence.

Five-step pipeline:
  1. JobBoardFetcher   (MCP: job_board)                       — live job postings
  2. SalaryFetcher     (MCP: salary_benchmark)                — compensation benchmarks
  3. TrendFetcher      (MCP: github_trends + social_signals)  — industry trends (parallel)
  4. SignalProcessor   (pure computation)                     — aggregate + rank signals
  5. TrendSummariser   (LLM)                                  — narrative summary

Steps 1–3 run concurrently via asyncio.gather. The agent tolerates partial
MCP failures — it returns whatever data it successfully retrieved, with
an empty list / None for unavailable sources.

Input (via context.user_profile):
  user_profile.target_role          : str | None — role to research
  user_profile.location             : str | None — country hint (e.g. "Zurich, CH")
  user_profile.skills               : list[str]  — used as GitHub trend topic hints

Output (AgentResult.output):
  role               : str
  country            : str
  job_postings       : list[dict]
  salary_benchmark   : dict | None
  trending_skills    : list[dict]
  industry_signals   : list[dict]
  market_summary     : str
  fetched_at         : str  (ISO 8601)
  data_sources       : list[str]
  processing_steps   : list[str]

Low-coupled: all five components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each stage so the client shows live progress.

Registration (at Celery worker startup):
    from agents.market_intelligence import MarketAgent
    from agents.core.agent_registry import registry
    registry.register(MarketAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    MARKET_JOB_POSTINGS_COUNT,
    MARKET_TRENDING_SKILLS_COUNT,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.market_intelligence.job_board_fetcher import JobBoardFetcher
from agents.market_intelligence.mcp_client import (
    HttpMCPClient,
    MCPClientProtocol,
    StubMCPClient,
)
from agents.market_intelligence.models import (
    IndustrySignal,
    JobPosting,
    MarketIntelligenceResult,
    SalaryBenchmark,
    TrendingSkill,
)
from agents.market_intelligence.salary_fetcher import SalaryFetcher
from agents.market_intelligence.signal_processor import SignalProcessor
from agents.market_intelligence.trend_fetcher import TrendFetcher
from agents.market_intelligence.trend_summariser import TrendSummariser

logger = get_logger(__name__)
_tracer = get_tracer("agents.market_intelligence.market_agent")

# ── Country extraction helpers ────────────────────────────────────────────────

_COUNTRY_ALIASES: dict[str, str] = {
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "frankreich": "FR",
    "united states": "US",
    "usa": "US",
    "united kingdom": "UK",
    "england": "UK",
    "britain": "UK",
    "switzerland": "CH",
    "schweiz": "CH",
    "suisse": "CH",
    "svizzera": "CH",
    "austria": "AT",
    "österreich": "AT",
    "netherlands": "NL",
    "holland": "NL",
    "spain": "ES",
    "españa": "ES",
    "italy": "IT",
    "italia": "IT",
    "canada": "CA",
    "australia": "AU",
    "japan": "JP",
    "singapore": "SG",
    "india": "IN",
}

_US_STATES = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    }
)


class MarketAgent(BaseAgent):
    """Retrieve and aggregate real-time job market signals for the user's target role.

    Parameters
    ----------
    job_board_fetcher:
        Fetches live job postings via MCP. Defaults to JobBoardFetcher with auto MCP client.
    salary_fetcher:
        Fetches salary benchmarks via MCP. Defaults to SalaryFetcher with auto MCP client.
    trend_fetcher:
        Fetches GitHub + social trend signals. Defaults to TrendFetcher with auto MCP client.
    signal_processor:
        Aggregates raw signals into domain objects. Defaults to ``SignalProcessor()``.
    trend_summariser:
        LLM narrative generator. Defaults to ``TrendSummariser`` with market model.
    event_publisher:
        Optional SSE event publisher. When ``None``, progress events are silently skipped.
    mcp_client:
        Explicit MCP client override. When set, all fetchers share this client unless they
        are also individually overridden.
    llm:
        LLM instance forwarded to ``TrendSummariser`` when not provided separately.
    """

    def __init__(
        self,
        *,
        job_board_fetcher: JobBoardFetcher | None = None,
        salary_fetcher: SalaryFetcher | None = None,
        trend_fetcher: TrendFetcher | None = None,
        signal_processor: SignalProcessor | None = None,
        trend_summariser: TrendSummariser | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        mcp_client: MCPClientProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        _client = mcp_client or _build_mcp_client()
        self._job_board_fetcher = job_board_fetcher or JobBoardFetcher(_client)
        self._salary_fetcher = salary_fetcher or SalaryFetcher(_client)
        self._trend_fetcher = trend_fetcher or TrendFetcher(_client)
        self._signal_processor = signal_processor or SignalProcessor()
        self._trend_summariser = trend_summariser or TrendSummariser(llm=llm)
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MARKET_INTELLIGENCE

    @property
    def display_name(self) -> str:
        return "Market Intelligence Agent"

    async def _execute(self, context: AgentContext) -> dict:
        with _tracer.start_as_current_span("market_intelligence.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            role = context.user_profile.target_role or "Software Engineer"
            country = _extract_country(context.user_profile.location)
            tech_hints = list(context.user_profile.skills)

            span.set_attribute("role", role)
            span.set_attribute("country", country)

            # ── Steps 1-3: Parallel MCP data fetching ─────────────────────
            self._emit_progress(
                context,
                "market_data_fetching",
                f"Fetching live market data for '{role}' in {country}…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="market.data_fetching").inc()

            job_postings, salary_benchmark, (github_trends, social_signals) = (
                await asyncio.gather(
                    self._job_board_fetcher.fetch(
                        role, country, correlation_id=context.correlation_id
                    ),
                    self._salary_fetcher.fetch(
                        role, country, correlation_id=context.correlation_id
                    ),
                    self._trend_fetcher.fetch(
                        tech_hints, correlation_id=context.correlation_id
                    ),
                )
            )

            # ── Step 4: Signal processing ──────────────────────────────────
            self._emit_progress(
                context,
                "signal_processing",
                "Aggregating and ranking market signals…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="market.signal_processing").inc()

            trending_skills = self._signal_processor.extract_trending_skills(
                job_postings, github_trends, social_signals
            )
            industry_signals = self._signal_processor.normalise_industry_signals(
                github_trends, social_signals, role
            )

            # ── Step 5: LLM summarisation ──────────────────────────────────
            self._emit_progress(
                context,
                "trend_summarisation",
                "Generating market intelligence narrative…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="market.summarisation").inc()

            market_summary = await self._trend_summariser.summarise(
                role,
                country,
                trending_skills,
                salary_benchmark,
                industry_signals,
                job_posting_count=len(job_postings),
                correlation_id=context.correlation_id,
            )

            # ── Observability ──────────────────────────────────────────────
            MARKET_TRENDING_SKILLS_COUNT.observe(len(trending_skills))
            MARKET_JOB_POSTINGS_COUNT.observe(len(job_postings))

            span.set_attribute("job_posting_count", len(job_postings))
            span.set_attribute("trending_skill_count", len(trending_skills))
            span.set_attribute("industry_signal_count", len(industry_signals))
            span.set_attribute("has_salary", salary_benchmark is not None)
            span.set_status(Status(StatusCode.OK))

            result = MarketIntelligenceResult(
                role=role,
                country=country,
                job_postings=job_postings,
                salary_benchmark=salary_benchmark,
                trending_skills=trending_skills,
                industry_signals=industry_signals,
                market_summary=market_summary,
                fetched_at=datetime.now(UTC),
                data_sources=_collect_data_sources(job_postings, salary_benchmark),
                processing_steps=[
                    "market_data_fetching",
                    "signal_processing",
                    "trend_summarisation",
                ],
            )

            logger.info(
                "market_intelligence.completed",
                role=role,
                country=country,
                job_posting_count=len(job_postings),
                trending_skill_count=len(trending_skills),
                has_salary=salary_benchmark is not None,
                correlation_id=context.correlation_id,
            )
            return _serialise(result)

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(
        self, context: AgentContext, step: str, description: str
    ) -> None:
        if self._event_publisher is None:
            return
        try:
            self._event_publisher.emit(
                AgentEvent(
                    event_type=AgentEventType.STEP_PROGRESS,
                    session_id=context.session_id,
                    user_id=context.user_id,
                    correlation_id=context.correlation_id,
                    payload={
                        "agent": self.agent_type.value,
                        "step": step,
                        "description": description,
                    },
                )
            )
        except Exception as exc:
            logger.warning(
                "market.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_mcp_client() -> MCPClientProtocol:
    """Auto-configure MCP client from environment settings.

    Uses HttpMCPClient when server URLs are configured; StubMCPClient otherwise.
    This means the agent works end-to-end in development without real MCP servers.
    """
    registry: dict[str, str] = {}
    if agent_settings.mcp_job_board_url:
        registry["job_board"] = agent_settings.mcp_job_board_url
    if agent_settings.mcp_salary_benchmark_url:
        registry["salary_benchmark"] = agent_settings.mcp_salary_benchmark_url
    if agent_settings.mcp_github_trends_url:
        registry["github_trends"] = agent_settings.mcp_github_trends_url
    if agent_settings.mcp_social_signals_url:
        registry["social_signals"] = agent_settings.mcp_social_signals_url

    if registry:
        return HttpMCPClient(registry, timeout_seconds=agent_settings.mcp_timeout_seconds)
    return StubMCPClient()


def _extract_country(location: str | None) -> str:
    """Best-effort ISO 2-letter country code extraction from a location string."""
    if not location:
        return "CH"

    parts = [p.strip() for p in location.split(",")]
    last = parts[-1].upper()

    # Two-letter alpha token as the last comma-separated component
    if len(last) == 2 and last.isalpha():
        # US state abbreviations (CA, NY, TX …) → country is US
        if last in _US_STATES:
            return "US"
        return last

    # Country name anywhere in the full string (e.g., "Berlin, Germany")
    lower = location.lower()
    for name, code in _COUNTRY_ALIASES.items():
        if name in lower:
            return code

    return "CH"


def _collect_data_sources(
    job_postings: list[JobPosting],
    salary_benchmark: SalaryBenchmark | None,
) -> list[str]:
    sources: set[str] = set()
    for p in job_postings:
        sources.add(p.source)
    if salary_benchmark:
        sources.add(salary_benchmark.source)
    return sorted(sources)


def _serialise(result: MarketIntelligenceResult) -> dict:
    return {
        "role": result.role,
        "country": result.country,
        "job_postings": [_serialise_posting(p) for p in result.job_postings],
        "salary_benchmark": _serialise_salary(result.salary_benchmark),
        "trending_skills": [_serialise_skill(s) for s in result.trending_skills],
        "industry_signals": [_serialise_signal(s) for s in result.industry_signals],
        "market_summary": result.market_summary,
        "fetched_at": result.fetched_at.isoformat(),
        "data_sources": result.data_sources,
        "processing_steps": result.processing_steps,
    }


def _serialise_posting(p: JobPosting) -> dict:
    return {
        "title": p.title,
        "company": p.company,
        "location": p.location,
        "required_skills": p.required_skills,
        "source": p.source,
        "posted_date": p.posted_date.isoformat() if p.posted_date else None,
        "salary_min": p.salary_min,
        "salary_max": p.salary_max,
        "currency": p.currency,
        "url": p.url,
    }


def _serialise_salary(b: SalaryBenchmark | None) -> dict | None:
    if b is None:
        return None
    return {
        "role": b.role,
        "country": b.country,
        "median_annual": b.median_annual,
        "p25_annual": b.p25_annual,
        "p75_annual": b.p75_annual,
        "currency": b.currency,
        "source": b.source,
        "freshness_date": b.freshness_date.isoformat() if b.freshness_date else None,
    }


def _serialise_skill(s: TrendingSkill) -> dict:
    return {
        "name": s.name,
        "category": s.category,
        "trend_direction": s.trend_direction.value,
        "signal_count": s.signal_count,
        "sources": s.sources,
        "evidence": s.evidence,
    }


def _serialise_signal(s: IndustrySignal) -> dict:
    return {
        "topic": s.topic,
        "signal_type": s.signal_type.value,
        "summary": s.summary,
        "source": s.source,
        "relevance_score": s.relevance_score,
        "url": s.url,
        "freshness_date": s.freshness_date.isoformat() if s.freshness_date else None,
    }
