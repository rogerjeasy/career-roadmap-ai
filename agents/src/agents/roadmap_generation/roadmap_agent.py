"""RoadmapAgent — L3 Specialist Agent: structured career roadmap generation.

Four-step pipeline:
  1. PhaseGenerator     (LLM: claude-sonnet-4-6)      — learning phases from gap + market
  2. MilestoneGenerator (LLM: claude-haiku-4-5)        — measurable checkpoints per phase
  3. WeeklyPlanner      (pure computation)              — weekly tasks + habit recommendations
  4. ResourceLinker     (RAG + catalog)                 — curated resources per phase

Steps 1→2 are sequential (milestones depend on phases).
Steps 3 and 4 run after step 2; both are pure computation (no I/O).

Input (via context.plan_snapshot + context.user_profile + context.rag_chunks):
  plan_snapshot["gap_analysis"]["prioritised_gaps"]        : list[dict]
  plan_snapshot["gap_analysis"]["dimension_scores"]        : dict
  plan_snapshot["market_intelligence"]["trending_skills"]  : list[dict]
  plan_snapshot["market_intelligence"]["salary_benchmark"] : dict | None
  plan_snapshot["market_intelligence"]["job_postings"]     : list[dict]
  plan_snapshot["market_intelligence"]["market_summary"]   : str
  user_profile.target_role                                 : str
  user_profile.timeline_months                             : int   (default 6)
  user_profile.weekly_hours_available                      : int   (default 10)
  rag_chunks                                               : list[RagChunk]

Output (AgentResult.output — strict JSON roadmap schema):
  roadmap_id       : str  (UUID)
  role             : str
  timeline_months  : int
  generated_at     : str  (ISO 8601)
  phases           : list[dict]
  milestones       : list[dict]
  weekly_schedule  : list[dict]
  habits           : list[dict]
  resources        : list[dict]
  summary          : str
  market_grounding : dict
  processing_steps : list[str]

Low-coupled: all four components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each stage so the client shows live progress.

Registration (at Celery worker startup):
    from agents.roadmap_generation import RoadmapAgent
    from agents.core.agent_registry import registry
    registry.register(RoadmapAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    ROADMAP_MILESTONE_COUNT,
    ROADMAP_PHASE_COUNT,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.roadmap_generation.milestone_generator import MilestoneGenerator
from agents.roadmap_generation.models import (
    Habit,
    Milestone,
    Phase,
    Resource,
    RoadmapResult,
    WeeklyTask,
)
from agents.roadmap_generation.phase_generator import PhaseGenerator
from agents.roadmap_generation.resource_linker import ResourceLinker
from agents.roadmap_generation.weekly_planner import WeeklyPlanner

logger = get_logger(__name__)
_tracer = get_tracer("agents.roadmap_generation.roadmap_agent")

_DEFAULT_TIMELINE_MONTHS = 6
_DEFAULT_WEEKLY_HOURS = 10


class RoadmapAgent(BaseAgent):
    """Generate a structured, phase-based career roadmap grounded in gap analysis and market data.

    Parameters
    ----------
    phase_generator:
        LLM phase builder. Defaults to ``PhaseGenerator()``.
    milestone_generator:
        LLM milestone builder. Defaults to ``MilestoneGenerator()``.
    weekly_planner:
        Pure-computation weekly scheduler. Defaults to ``WeeklyPlanner()``.
    resource_linker:
        RAG + catalog resource linker. Defaults to ``ResourceLinker()``.
    event_publisher:
        Optional SSE publisher for STEP_PROGRESS events.
    llm:
        Override LLM forwarded to both LLM-dependent components when not explicitly provided.
    """

    def __init__(
        self,
        *,
        phase_generator: PhaseGenerator | None = None,
        milestone_generator: MilestoneGenerator | None = None,
        weekly_planner: WeeklyPlanner | None = None,
        resource_linker: ResourceLinker | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._phase_generator = phase_generator or PhaseGenerator(llm=llm)
        self._milestone_generator = milestone_generator or MilestoneGenerator(llm=llm)
        self._weekly_planner = weekly_planner or WeeklyPlanner()
        self._resource_linker = resource_linker or ResourceLinker()
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROADMAP_GENERATION

    @property
    def display_name(self) -> str:
        return "Roadmap Generation Agent"

    async def _execute(self, context: AgentContext) -> dict:
        with _tracer.start_as_current_span("roadmap_generation.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            # ── Extract inputs ─────────────────────────────────────────────
            target_role: str = context.user_profile.target_role or "Software Engineer"
            timeline_months: int = (
                context.user_profile.timeline_months or _DEFAULT_TIMELINE_MONTHS
            )
            weekly_hours: int = (
                context.user_profile.weekly_hours_available or _DEFAULT_WEEKLY_HOURS
            )

            gap_analysis: dict = context.plan_snapshot.get("gap_analysis", {})
            market_intel: dict = context.plan_snapshot.get("market_intelligence", {})

            prioritised_gaps: list[dict] = gap_analysis.get("prioritised_gaps", [])
            trending_skills: list[dict] = market_intel.get("trending_skills", [])
            salary_benchmark: dict | None = market_intel.get("salary_benchmark")
            job_postings: list[dict] = market_intel.get("job_postings", [])

            span.set_attribute("target_role", target_role)
            span.set_attribute("timeline_months", timeline_months)
            span.set_attribute("gap_count", len(prioritised_gaps))

            # ── Step 1: Phase generation ────────────────────────────────────
            self._emit_progress(
                context,
                "phase_generation",
                f"Generating learning phases for '{target_role}' over {timeline_months} months…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="roadmap.phase_generation").inc()

            phases = await self._phase_generator.generate(
                target_role,
                timeline_months,
                weekly_hours,
                prioritised_gaps,
                trending_skills,
                salary_benchmark,
                len(job_postings),
                correlation_id=context.correlation_id,
            )

            # ── Step 2: Milestone generation ────────────────────────────────
            self._emit_progress(
                context,
                "milestone_generation",
                "Creating measurable milestones and success criteria…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="roadmap.milestone_generation").inc()

            milestones = await self._milestone_generator.generate(
                phases,
                target_role,
                correlation_id=context.correlation_id,
            )

            # ── Step 3: Weekly planning (pure computation) ─────────────────
            self._emit_progress(
                context,
                "weekly_planning",
                "Building week-by-week schedule and habit recommendations…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="roadmap.weekly_planning").inc()

            weekly_schedule, habits = self._weekly_planner.plan(
                phases,
                milestones,
                timeline_months,
                weekly_hours,
                target_role=target_role,
            )

            # ── Step 4: Resource linking (RAG + catalog) ───────────────────
            self._emit_progress(
                context,
                "resource_linking",
                "Matching curated learning resources to each phase…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="roadmap.resource_linking").inc()

            resources = self._resource_linker.link(
                phases,
                context.rag_chunks,
                trending_skills,
            )

            # ── Observability ──────────────────────────────────────────────
            ROADMAP_PHASE_COUNT.observe(len(phases))
            ROADMAP_MILESTONE_COUNT.observe(len(milestones))

            span.set_attribute("phase_count", len(phases))
            span.set_attribute("milestone_count", len(milestones))
            span.set_attribute("weekly_task_count", len(weekly_schedule))
            span.set_attribute("resource_count", len(resources))
            span.set_status(Status(StatusCode.OK))

            result = RoadmapResult(
                role=target_role,
                timeline_months=timeline_months,
                phases=phases,
                milestones=milestones,
                weekly_schedule=weekly_schedule,
                habits=habits,
                resources=resources,
                summary=_build_summary(target_role, timeline_months, phases, milestones, trending_skills),
                market_grounding=_build_market_grounding(market_intel, trending_skills, salary_benchmark),
                processing_steps=[
                    "phase_generation",
                    "milestone_generation",
                    "weekly_planning",
                    "resource_linking",
                ],
            )

            logger.info(
                "roadmap_generation.completed",
                target_role=target_role,
                timeline_months=timeline_months,
                phase_count=len(phases),
                milestone_count=len(milestones),
                weekly_task_count=len(weekly_schedule),
                correlation_id=context.correlation_id,
            )
            return _serialise(result)

    # ── Private helpers ────────────────────────────────────────────────────

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
            logger.warning("roadmap.progress_emit_failed", step=step, error=str(exc))


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_summary(
    role: str,
    timeline_months: int,
    phases: list[Phase],
    milestones: list[Milestone],
    trending_skills: list[dict],
) -> str:
    parts = [
        f"Your personalised roadmap to {role} spans {timeline_months} months "
        f"across {len(phases)} structured learning phases."
    ]
    if phases:
        parts.append(
            f"The phases progress through: {' → '.join(p.title for p in phases)}."
        )
    top_skills = [s["name"] for s in trending_skills[:3]]
    if top_skills:
        parts.append(f"Market-priority skills incorporated: {', '.join(top_skills)}.")
    if milestones:
        parts.append(
            f"You will hit {len(milestones)} measurable milestones, each producing "
            f"a concrete portfolio deliverable."
        )
    return " ".join(parts)


def _build_market_grounding(
    market_intel: dict,
    trending_skills: list[dict],
    salary_benchmark: dict | None,
) -> dict:
    return {
        "market_summary": market_intel.get("market_summary", ""),
        "top_trending_skills": [s["name"] for s in trending_skills[:5]],
        "job_posting_count": len(market_intel.get("job_postings", [])),
        "salary_median": salary_benchmark.get("median_annual") if salary_benchmark else None,
        "salary_currency": salary_benchmark.get("currency") if salary_benchmark else None,
        "country": market_intel.get("country", ""),
    }


# ── Serialisers ───────────────────────────────────────────────────────────────


def _serialise(result: RoadmapResult) -> dict:
    return {
        "roadmap_id": result.roadmap_id,
        "role": result.role,
        "timeline_months": result.timeline_months,
        "generated_at": result.generated_at.isoformat(),
        "phases": [_serialise_phase(p) for p in result.phases],
        "milestones": [_serialise_milestone(m) for m in result.milestones],
        "weekly_schedule": [_serialise_weekly_task(t) for t in result.weekly_schedule],
        "habits": [_serialise_habit(h) for h in result.habits],
        "resources": [_serialise_resource(r) for r in result.resources],
        "summary": result.summary,
        "market_grounding": result.market_grounding,
        "processing_steps": result.processing_steps,
    }


def _serialise_phase(p: Phase) -> dict:
    return {
        "index": p.index,
        "title": p.title,
        "description": p.description,
        "duration_weeks": p.duration_weeks,
        "goals": p.goals,
        "skills_to_acquire": p.skills_to_acquire,
        "skills": [
            {"text": s.text, "is_priority": s.is_priority, "display_order": s.display_order}
            for s in p.skills
        ],
        "actions": [
            {"text": a.text, "sub_text": a.sub_text, "display_order": a.display_order}
            for a in p.actions
        ],
        "gaps_addressed": p.gaps_addressed,
        "market_relevance": p.market_relevance,
        "difficulty": p.difficulty.value,
    }


def _serialise_milestone(m: Milestone) -> dict:
    return {
        "name": m.name,
        "description": m.description,
        "phase_index": m.phase_index,
        "week_number": m.week_number,
        "icon": m.icon,
        "success_criteria": m.success_criteria,
        "skills_demonstrated": m.skills_demonstrated,
        "deliverable": m.deliverable,
    }


def _serialise_weekly_task(t: WeeklyTask) -> dict:
    return {
        "week_number": t.week_number,
        "phase_index": t.phase_index,
        "focus_area": t.focus_area,
        "tasks": t.tasks,
        "estimated_hours": t.estimated_hours,
        "deliverable": t.deliverable,
    }


def _serialise_habit(h: Habit) -> dict:
    return {
        "name": h.name,
        "frequency": h.frequency,
        "duration_minutes": h.duration_minutes,
        "rationale": h.rationale,
        "phase_start": h.phase_start,
    }


def _serialise_resource(r: Resource) -> dict:
    return {
        "title": r.title,
        "resource_type": r.resource_type.value,
        "provider": r.provider,
        "difficulty": r.difficulty.value,
        "tags": r.tags,
        "url": r.url,
        "estimated_hours": r.estimated_hours,
        "is_free": r.is_free,
        "description": r.description,
        "phase_index": r.phase_index,
    }
