"""NetworkingAgent — L3 Specialist Agent: networking strategy and outreach.

Four-step pipeline (steps 1+2 run concurrently):
  1. LinkedInReviewer    (MCP: linkedin_profile + LLM)  — profile scoring & improvement plan
  2. EventFinder         (MCP: industry_news)            — relevant events & communities
  3. OutreachDrafter     (LLM)                           — personalised outreach message drafts
  4. RelationshipTracker (pure computation)              — relationship pipeline seeding

Input (via context.plan_snapshot + context.user_profile):
  plan_snapshot["gap_analysis"]["prioritised_gaps"] : list[dict]  — from GapAgent
  plan_snapshot["cv_analysis"]["parsed_cv"]          : dict       — structured CV
  user_profile.target_role                            : str
  user_profile.current_role                           : str | None
  user_profile.location                              : str | None
  user_profile.skills                                : list[str]
  context.plan_snapshot.get("payload", {}).get("linkedin_profile_url") : str | None

Output (AgentResult.output):
  target_role              : str
  linkedin_review          : dict | None    — LinkedInProfileScore fields
  events_and_communities   : list[dict]     — CommunityEvent objects
  outreach_drafts          : list[dict]     — OutreachDraft objects
  relationship_pipeline    : dict           — RelationshipPipeline fields
  data_sources             : list[str]
  generated_at             : str            — ISO 8601
  processing_steps         : list[str]

Low-coupled: all four components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each step so the client shows live progress.

Registration (at Celery worker startup):
    from agents.networking import NetworkingAgent
    from agents.core.agent_registry import registry
    registry.register(NetworkingAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    NET_CONTACTS_TRACKED,
    NET_EVENTS_FOUND,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.networking.event_finder import EventFinder
from agents.networking.linkedin_reviewer import LinkedInReviewer
from agents.networking.mcp_client import (
    HttpMCPClient,
    MCPClientProtocol,
    StubMCPClient,
)
from agents.networking.models import (
    CommunityEvent,
    LinkedInProfileScore,
    NetworkingResult,
    OutreachDraft,
    RelationshipPipeline,
)
from agents.networking.outreach_drafter import OutreachDrafter
from agents.networking.relationship_tracker import RelationshipTracker

logger = get_logger(__name__)
_tracer = get_tracer("agents.networking.networking_agent")

_MAX_TARGET_GAPS = 3


class NetworkingAgent(BaseAgent):
    """Build a complete networking strategy: LinkedIn review, events, outreach, pipeline.

    Parameters
    ----------
    linkedin_reviewer:
        MCP + LLM profile reviewer. Defaults to ``LinkedInReviewer()``.
    event_finder:
        MCP-backed event discoverer. Defaults to ``EventFinder`` with auto MCP.
    outreach_drafter:
        LLM outreach message generator. Defaults to ``OutreachDrafter()``.
    relationship_tracker:
        Pure-computation pipeline builder. Defaults to ``RelationshipTracker()``.
    event_publisher:
        Optional SSE progress publisher. When ``None``, progress events are skipped.
    mcp_client:
        Explicit MCP client override shared by LinkedIn reviewer and event finder.
    max_events:
        Maximum events/communities to return per run (default 10).
    """

    def __init__(
        self,
        *,
        linkedin_reviewer: LinkedInReviewer | None = None,
        event_finder: EventFinder | None = None,
        outreach_drafter: OutreachDrafter | None = None,
        relationship_tracker: RelationshipTracker | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        mcp_client: MCPClientProtocol | None = None,
        max_events: int = 10,
    ) -> None:
        _client = mcp_client or _build_mcp_client()
        self._linkedin_reviewer = linkedin_reviewer or LinkedInReviewer()
        self._event_finder = event_finder or EventFinder(_client, max_events=max_events)
        self._outreach_drafter = outreach_drafter or OutreachDrafter(
            max_drafts=agent_settings.networking_max_outreach_drafts
        )
        self._relationship_tracker = relationship_tracker or RelationshipTracker()
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.NETWORKING

    @property
    def display_name(self) -> str:
        return "Networking & Outreach Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full networking pipeline and return structured output."""
        with _tracer.start_as_current_span("networking.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            target_role = context.user_profile.target_role or "Software Engineer"
            span.set_attribute("target_role", target_role)

            gap_analysis = context.plan_snapshot.get("gap_analysis", {})
            cv_analysis = context.plan_snapshot.get("cv_analysis", {})
            prioritised_gaps: list[dict] = gap_analysis.get("prioritised_gaps", [])[:_MAX_TARGET_GAPS]
            parsed_cv: dict[str, Any] = cv_analysis.get("parsed_cv", {})
            linkedin_url: str | None = (
                context.plan_snapshot
                .get("payload", {})
                .get("linkedin_profile_url")
            )

            top_gap_name = _resolve_top_gap(prioritised_gaps, context)
            span.set_attribute("top_gap", top_gap_name)
            span.set_attribute("gap_count", len(prioritised_gaps))

            # ── Steps 1 + 2: LinkedIn review + event finding (concurrent) ──
            self._emit_progress(
                context,
                "linkedin_review",
                "Reviewing LinkedIn profile and discovering events…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="net.linkedin_review").inc()
            STEP_PROGRESS_TOTAL.labels(step_name="net.event_finding").inc()

            linkedin_review, events = await asyncio.gather(
                self._safe_linkedin_review(parsed_cv, target_role, linkedin_url, context.correlation_id),
                self._event_finder.find(
                    target_role=target_role,
                    skills=context.user_profile.skills[:5],
                    location=context.user_profile.location,
                    correlation_id=context.correlation_id,
                ),
                return_exceptions=False,
            )

            NET_EVENTS_FOUND.observe(len(events))

            # ── Step 3: Outreach drafting ──────────────────────────────────
            self._emit_progress(
                context,
                "outreach_drafting",
                f"Drafting outreach messages for '{top_gap_name}'…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="net.outreach_drafting").inc()

            background = _build_background_summary(parsed_cv, context.user_profile)
            outreach_drafts = await self._outreach_drafter.draft(
                target_role=target_role,
                current_role=context.user_profile.current_role,
                top_skill_gap=top_gap_name,
                background_summary=background,
                correlation_id=context.correlation_id,
            )

            # ── Step 4: Relationship pipeline seeding ──────────────────────
            self._emit_progress(
                context,
                "pipeline_building",
                "Building relationship pipeline…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="net.pipeline_building").inc()

            pipeline = self._relationship_tracker.build_pipeline(
                prioritised_gaps=prioritised_gaps,
                outreach_drafts=outreach_drafts,
                target_role=target_role,
                correlation_id=context.correlation_id,
            )

            NET_CONTACTS_TRACKED.observe(pipeline.total_contacts)

            # ── Observability ──────────────────────────────────────────────
            linkedin_score = linkedin_review.overall_score if linkedin_review else 0.0
            span.set_attribute("events_found", len(events))
            span.set_attribute("outreach_draft_count", len(outreach_drafts))
            span.set_attribute("contacts_tracked", pipeline.total_contacts)
            span.set_attribute("linkedin_overall_score", linkedin_score)
            span.set_status(Status(StatusCode.OK))

            data_sources = _collect_data_sources(events, linkedin_review)

            logger.info(
                "networking.completed",
                target_role=target_role,
                events_found=len(events),
                outreach_draft_count=len(outreach_drafts),
                contacts_tracked=pipeline.total_contacts,
                linkedin_overall_score=linkedin_score,
                correlation_id=context.correlation_id,
            )

            result = NetworkingResult(
                target_role=target_role,
                linkedin_review=linkedin_review,
                events_and_communities=events,
                outreach_drafts=outreach_drafts,
                relationship_pipeline=pipeline,
                data_sources=data_sources,
                processing_steps=[
                    "linkedin_review",
                    "event_finding",
                    "outreach_drafting",
                    "pipeline_building",
                ],
            )
            return _serialise(result)

    # ── Private helpers ────────────────────────────────────────────────────

    async def _safe_linkedin_review(
        self,
        parsed_cv: dict[str, Any],
        target_role: str,
        linkedin_url: str | None,
        correlation_id: str,
    ) -> LinkedInProfileScore | None:
        """Run LinkedIn review; gracefully return None if profile data is missing."""
        try:
            profile_data = dict(parsed_cv)
            if linkedin_url:
                profile_data["linkedin_url"] = linkedin_url
            return await self._linkedin_reviewer.review(
                profile_data, target_role, correlation_id=correlation_id
            )
        except Exception as exc:
            logger.warning(
                "networking.linkedin_review_skipped",
                error=str(exc),
                correlation_id=correlation_id,
            )
            return None

    def _emit_progress(self, context: AgentContext, step: str, description: str) -> None:
        """Best-effort STEP_PROGRESS event emission. Never raises."""
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
                "networking.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_mcp_client() -> MCPClientProtocol:
    """Auto-configure MCP client from environment settings.

    Uses HttpMCPClient when server URLs are configured; StubMCPClient otherwise.
    """
    registry: dict[str, str] = {}
    if agent_settings.mcp_linkedin_profile_url:
        registry["linkedin_profile"] = agent_settings.mcp_linkedin_profile_url
    if agent_settings.mcp_industry_news_url:
        registry["industry_news"] = agent_settings.mcp_industry_news_url
    if registry:
        return HttpMCPClient(registry, timeout_seconds=agent_settings.mcp_timeout_seconds)
    return StubMCPClient()


def _resolve_top_gap(prioritised_gaps: list[dict], context: AgentContext) -> str:
    """Return the name of the top-priority skill gap."""
    if prioritised_gaps:
        name = str(prioritised_gaps[0].get("requirement_name", ""))
        if name:
            return name
    if context.user_profile.skills:
        return context.user_profile.skills[0]
    return context.user_profile.target_role or "the target role"


def _build_background_summary(parsed_cv: dict[str, Any], user_profile: Any) -> str:
    """Build a concise background summary for outreach message context."""
    parts: list[str] = []

    if user_profile.current_role:
        parts.append(f"Current role: {user_profile.current_role}")

    if user_profile.skills:
        parts.append(f"Key skills: {', '.join(user_profile.skills[:5])}")

    experience = parsed_cv.get("experience", [])
    if isinstance(experience, list) and experience:
        latest = experience[0]
        if isinstance(latest, dict):
            title = latest.get("title", "")
            company = latest.get("company", "")
            if title and company:
                parts.append(f"Most recent: {title} at {company}")

    return ". ".join(parts) if parts else "Career professional in transition"


def _collect_data_sources(
    events: list[CommunityEvent],
    linkedin_review: LinkedInProfileScore | None,
) -> list[str]:
    sources: set[str] = set()
    for event in events:
        sources.add(event.source)
    if linkedin_review is not None:
        sources.add("mcp_linkedin_profile")
    sources.add("llm_outreach_drafter")
    sources.add("llm_linkedin_reviewer")
    return sorted(sources)


# ── Output serialisers ────────────────────────────────────────────────────────


def _serialise(result: NetworkingResult) -> dict:
    return {
        "target_role": result.target_role,
        "linkedin_review": (
            _serialise_linkedin_review(result.linkedin_review)
            if result.linkedin_review else None
        ),
        "events_and_communities": [_serialise_event(e) for e in result.events_and_communities],
        "outreach_drafts": [_serialise_draft(d) for d in result.outreach_drafts],
        "relationship_pipeline": (
            _serialise_pipeline(result.relationship_pipeline)
            if result.relationship_pipeline else None
        ),
        "data_sources": result.data_sources,
        "generated_at": result.generated_at.isoformat(),
        "processing_steps": result.processing_steps,
    }


def _serialise_linkedin_review(review: LinkedInProfileScore) -> dict:
    return {
        "headline_score": review.headline_score,
        "summary_score": review.summary_score,
        "experience_score": review.experience_score,
        "skills_score": review.skills_score,
        "overall_score": review.overall_score,
        "ats_score": review.ats_score,
        "strengths": review.strengths,
        "improvements": review.improvements,
        "recommended_keywords": review.recommended_keywords,
    }


def _serialise_event(event: CommunityEvent) -> dict:
    return {
        "event_id": event.event_id,
        "title": event.title,
        "event_type": event.event_type.value,
        "platform": event.platform,
        "skill_tags": event.skill_tags,
        "relevance_score": event.relevance_score,
        "description": event.description,
        "url": event.url,
        "date": event.date,
        "location": event.location,
        "is_online": event.is_online,
        "source": event.source,
    }


def _serialise_draft(draft: OutreachDraft) -> dict:
    return {
        "draft_id": draft.draft_id,
        "recipient_type": draft.recipient_type.value,
        "subject": draft.subject,
        "body": draft.body,
        "tone": draft.tone.value,
        "platform": draft.platform,
        "target_skill": draft.target_skill,
        "call_to_action": draft.call_to_action,
        "estimated_response_rate": draft.estimated_response_rate,
    }


def _serialise_pipeline(pipeline: RelationshipPipeline) -> dict:
    return {
        "total_contacts": pipeline.total_contacts,
        "by_status": pipeline.by_status,
        "contacts": [
            {
                "contact_id": c.contact_id,
                "role": c.role,
                "recipient_type": c.recipient_type.value,
                "connection_status": c.connection_status.value,
                "target_skill": c.target_skill,
                "source": c.source,
                "name": c.name,
                "company": c.company,
                "notes": c.notes,
            }
            for c in pipeline.contacts
        ],
        "next_actions": pipeline.next_actions,
        "outreach_priority_skills": pipeline.outreach_priority_skills,
    }
