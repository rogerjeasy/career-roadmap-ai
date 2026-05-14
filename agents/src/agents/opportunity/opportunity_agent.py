"""OpportunityAgent — L3 Specialist Agent: job matching, scoring, and CV tailoring.

Responsibilities:
  1. Fetch live job listings via the job-board MCP server.
  2. Score every listing against the user profile (deterministic + LLM enrichment).
  3. Identify high-match roles (score ≥ 0.65) and emit match alerts.
  4. Generate tailored CV snippets for the top high-match jobs.
  5. Extract target companies worth tracking.

Runs in Phase 5 in parallel with LearningResourceAgent and NetworkingAgent.
Observable: OTel spans, STEP_PROGRESS SSE events, Prometheus counters/histograms.

Registration (Celery worker startup):
    from agents.bus.publisher import EventPublisher
    from agents.opportunity import OpportunityAgent
    from agents.core.agent_registry import registry

    registry.register(OpportunityAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    OPP_HIGH_MATCH_COUNT,
    OPP_JOB_FETCH_DURATION,
    OPP_JOB_FETCH_TOTAL,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.config import agent_settings
from agents.opportunity.cv_tailor import CVTailor
from agents.opportunity.job_scorer import JobScorer
from agents.opportunity.mcp_client import JobBoardClientProtocol, JobBoardMCPClient
from agents.opportunity.models import (
    JobMatchScore,
    OpportunityOutput,
    TargetCompany,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.opportunity.opportunity_agent")

_HIGH_MATCH_THRESHOLD = 0.65
_DEFAULT_FETCH_LIMIT = 50


def _default_model() -> str:
    return agent_settings.opportunity_model


class OpportunityAgent(BaseAgent):
    """Job matching, scoring, and CV-tailoring specialist agent.

    Parameters
    ----------
    event_publisher:
        Optional SSE event publisher. When ``None`` (e.g. in unit tests),
        progress events are silently skipped.
    llm:
        Override the LangChain LLM client (useful in tests).
    job_board_client:
        Override the MCP job-board client (useful in tests).
    job_scorer:
        Override the JobScorer (useful in tests).
    cv_tailor:
        Override the CVTailor (useful in tests).
    """

    def __init__(
        self,
        *,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
        job_board_client: JobBoardClientProtocol | None = None,
        job_scorer: JobScorer | None = None,
        cv_tailor: CVTailor | None = None,
    ) -> None:
        self._event_publisher = event_publisher
        self._llm = llm or ChatAnthropic(
            model=_default_model(),
            max_tokens=4096,
            temperature=0.1,
        )
        self._job_board_client = job_board_client or JobBoardMCPClient()
        self._job_scorer = job_scorer or JobScorer(llm=self._llm)
        self._cv_tailor = cv_tailor or CVTailor(llm=self._llm)

    # ── BaseAgent contract ─────────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.OPPORTUNITY

    @property
    def display_name(self) -> str:
        return "Opportunity Matcher"

    async def _execute(self, context: AgentContext) -> dict:
        with _tracer.start_as_current_span("opportunity.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            profile = context.user_profile

            # ── Step 1: Fetch job listings ─────────────────────────────────
            self._emit_progress(context, "job_fetch", "Searching live job listings…")
            STEP_PROGRESS_TOTAL.labels(step_name="opportunity.job_fetch").inc()

            listings = await self._fetch_listings(context)
            span.set_attribute("listings_fetched", len(listings))

            if not listings:
                logger.warning(
                    "opportunity.no_listings",
                    target_role=profile.target_role,
                    correlation_id=context.correlation_id,
                )
                span.set_status(Status(StatusCode.OK))
                return _empty_output(profile).model_dump()

            # ── Step 2: Score all listings deterministically ───────────────
            self._emit_progress(context, "scoring", f"Scoring {len(listings)} opportunities…")
            STEP_PROGRESS_TOTAL.labels(step_name="opportunity.scoring").inc()

            scored = self._job_scorer.score_all(listings, profile)

            # ── Step 3: LLM enrichment for top results ─────────────────────
            self._emit_progress(context, "enrichment", "Analysing top matches in depth…")
            STEP_PROGRESS_TOTAL.labels(step_name="opportunity.enrichment").inc()

            scored = await self._job_scorer.enrich_top(scored, profile)

            high_match = [j for j in scored if j.is_high_match]
            OPP_HIGH_MATCH_COUNT.observe(len(high_match))
            span.set_attribute("high_match_count", len(high_match))

            # ── Step 4: CV tailoring for top high-match jobs ───────────────
            cv_tailoring = []
            if high_match:
                self._emit_progress(context, "cv_tailoring", "Tailoring your CV for top matches…")
                STEP_PROGRESS_TOTAL.labels(step_name="opportunity.cv_tailoring").inc()
                cv_tailoring = await self._cv_tailor.tailor(high_match, profile)

            # ── Step 5: Extract target companies ──────────────────────────
            target_companies = _extract_target_companies(high_match)

            # ── Step 6: Build match alerts ─────────────────────────────────
            alerts = _build_alerts(high_match)

            span.set_status(Status(StatusCode.OK))
            logger.info(
                "opportunity.completed",
                listings_fetched=len(listings),
                high_match=len(high_match),
                cv_snippets=len(cv_tailoring),
                target_companies=len(target_companies),
                correlation_id=context.correlation_id,
            )

            output = OpportunityOutput(
                total_listings_fetched=len(listings),
                scored_jobs=scored[:20],
                high_match_jobs=high_match,
                cv_tailoring=cv_tailoring,
                target_companies=target_companies,
                match_alerts=alerts,
                search_query=profile.target_role or "",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            return output.model_dump()

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _fetch_listings(self, context: AgentContext) -> list:
        profile = context.user_profile
        t0 = time.monotonic()
        try:
            listings = await self._job_board_client.search_jobs(
                role=profile.target_role or "",
                location=profile.location,
                skills=profile.skills[:10],
                limit=_DEFAULT_FETCH_LIMIT,
            )
            OPP_JOB_FETCH_TOTAL.labels(status="success").inc()
            return listings
        except Exception as exc:
            logger.warning(
                "opportunity.fetch_failed",
                error=str(exc),
                correlation_id=context.correlation_id,
            )
            OPP_JOB_FETCH_TOTAL.labels(status="error").inc()
            return []
        finally:
            OPP_JOB_FETCH_DURATION.observe(time.monotonic() - t0)

    def _emit_progress(self, context: AgentContext, step: str, description: str) -> None:
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
            logger.warning("opportunity.progress_emit_failed", step=step, error=str(exc))


# ── Module-level helpers ───────────────────────────────────────────────────────


def _extract_target_companies(high_match: list[JobMatchScore]) -> list[TargetCompany]:
    company_jobs: dict[str, list[JobMatchScore]] = {}
    for job in high_match:
        company_jobs.setdefault(job.listing.company, []).append(job)

    companies = []
    for company, jobs in company_jobs.items():
        avg_score = sum(j.match_score for j in jobs) / len(jobs)
        top_roles = list({j.listing.title for j in jobs})[:3]
        if len(jobs) >= 2 or avg_score >= 0.75:
            companies.append(TargetCompany(
                name=company,
                reason=f"{len(jobs)} matching role(s) with avg {avg_score:.0%} fit.",
                job_count=len(jobs),
                top_roles=top_roles,
                avg_match_score=round(avg_score, 3),
            ))

    companies.sort(key=lambda c: (-c.job_count, -c.avg_match_score))
    return companies[:10]


def _build_alerts(high_match: list[JobMatchScore]) -> list[str]:
    alerts = []
    for job in high_match[:5]:
        score_pct = f"{job.match_score:.0%}"
        alert = f"Strong match ({score_pct}): {job.listing.title} at {job.listing.company}"
        if job.listing.location:
            alert += f" — {job.listing.location}"
        alerts.append(alert)
    return alerts


def _empty_output(profile: Any) -> OpportunityOutput:
    return OpportunityOutput(
        total_listings_fetched=0,
        search_query=getattr(profile, "target_role", "") or "",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
