"""GapAgent — L3 Specialist Agent: gap analysis between candidate profile and target role.

Three-step pipeline:
  1. Role Profiling     (RoleProfiler)    — LLM: enumerate role requirements & keywords
  2. Skill Gap Scoring  (SkillGapScorer)  — LLM + heuristic: identify & score gaps per dimension
  3. Gap Prioritisation (GapPrioritiser)  — pure computation: rank gaps by ROI × urgency

Input (via context.plan_snapshot + context.user_profile):
  plan_snapshot["cv_analysis"]["skill_graph"] : dict  — normalised skills from CV analysis
  plan_snapshot["cv_analysis"]["parsed_cv"]   : dict  — structured CV (experience, certs, …)
  user_profile.target_role                    : str   — role to close gaps towards
  user_profile.timeline_months                : int   — influences urgency ranking
  user_profile.weekly_hours_available         : int   — influences urgency ranking

Output (AgentResult.output):
  role_profile       : dict   — requirements, keywords, typical experience
  skill_gaps         : list   — each gap: name, dimension, severity, diff_score, …
  dimension_scores   : dict   — tech/soft/cert/portfolio/keyword gap scores (0–1)
  overall_diff_score : float  — weighted composite gap score (0=no gap, 1=full gap)
  prioritised_gaps   : list   — gaps re-ranked by priority (1=highest)
  processing_steps   : list[str]

Low-coupled: all three components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each step so the client shows live progress.

Registration (at Celery worker startup):
    from agents.gap_analysis import GapAgent
    from agents.core.agent_registry import registry
    registry.register(GapAgent(event_publisher=EventPublisher(redis_client)))
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
    GAP_DIFF_SCORE,
    GAP_GAP_COUNT,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.gap_analysis.gap_prioritiser import GapPrioritiser
from agents.gap_analysis.models import DimensionScores, RoleProfile, SkillGap
from agents.gap_analysis.role_profiler import RoleProfiler
from agents.gap_analysis.skill_gap_scorer import SkillGapScorer

logger = get_logger(__name__)
_tracer = get_tracer("agents.gap_analysis.gap_agent")

# Dimension weights for overall_diff_score (must sum to 1.0)
_DIM_WEIGHTS = {
    "tech_skills": 0.45,
    "soft_skills": 0.20,
    "certifications": 0.15,
    "portfolio": 0.10,
    "keywords": 0.10,
}


class GapAgent(BaseAgent):
    """Identify, score, and prioritise gaps between a candidate and their target role.

    Parameters
    ----------
    role_profiler:
        LLM-based role requirements builder. Defaults to ``RoleProfiler()``.
    skill_gap_scorer:
        LLM + heuristic gap scorer. Defaults to ``SkillGapScorer()``.
    gap_prioritiser:
        Pure-computation gap ranker. Defaults to ``GapPrioritiser()``.
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events. When ``None``
        progress events are silently skipped (e.g. in unit tests).
    llm:
        Override LLM forwarded to LLM-dependent components when not explicitly provided.
    """

    def __init__(
        self,
        *,
        role_profiler: RoleProfiler | None = None,
        skill_gap_scorer: SkillGapScorer | None = None,
        gap_prioritiser: GapPrioritiser | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._role_profiler = role_profiler or RoleProfiler(llm=llm)
        self._skill_gap_scorer = skill_gap_scorer or SkillGapScorer(llm=llm)
        self._gap_prioritiser = gap_prioritiser or GapPrioritiser()
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.GAP_ANALYSIS

    @property
    def display_name(self) -> str:
        return "Gap Analysis Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full gap analysis pipeline and return structured output."""
        with _tracer.start_as_current_span("gap_analysis.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            target_role: str = context.user_profile.target_role or ""
            cv_analysis: dict = context.plan_snapshot.get("cv_analysis", {})
            skill_graph_dict: dict = cv_analysis.get("skill_graph", {})
            parsed_cv_dict: dict = cv_analysis.get("parsed_cv", {})

            # Prefer normalised skill names from CV analysis; fall back to profile skills.
            candidate_skills: list[str] = [
                node["canonical_name"]
                for node in skill_graph_dict.get("nodes", [])
                if node.get("canonical_name")
            ]
            if not candidate_skills:
                candidate_skills = list(context.user_profile.skills)

            span.set_attribute("target_role", target_role)
            span.set_attribute("candidate_skill_count", len(candidate_skills))

            # ── Step 1: Role profiling ──────────────────────────────────────
            self._emit_progress(
                context, "role_profiling", f"Profiling requirements for '{target_role}'…"
            )
            STEP_PROGRESS_TOTAL.labels(step_name="gap.role_profiling").inc()

            role_profile = await self._role_profiler.profile(
                target_role, correlation_id=context.correlation_id
            )

            # ── Step 2: Skill gap scoring ──────────────────────────────────
            self._emit_progress(context, "skill_gap_scoring", "Scoring skill gaps…")
            STEP_PROGRESS_TOTAL.labels(step_name="gap.skill_gap_scoring").inc()

            gaps, dimension_scores = await self._skill_gap_scorer.score(
                candidate_skills,
                parsed_cv_dict,
                role_profile,
                correlation_id=context.correlation_id,
            )

            # ── Step 3: Gap prioritisation ─────────────────────────────────
            self._emit_progress(
                context, "gap_prioritisation", "Prioritising gaps by ROI & urgency…"
            )
            STEP_PROGRESS_TOTAL.labels(step_name="gap.gap_prioritisation").inc()

            prioritised = self._gap_prioritiser.prioritise(
                gaps,
                timeline_months=context.user_profile.timeline_months,
                weekly_hours=context.user_profile.weekly_hours_available,
                correlation_id=context.correlation_id,
            )

            overall_diff = _compute_overall_diff(dimension_scores)

            GAP_DIFF_SCORE.observe(overall_diff)
            GAP_GAP_COUNT.observe(len(gaps))

            span.set_attribute("gap_count", len(gaps))
            span.set_attribute("overall_diff_score", overall_diff)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "gap_analysis.completed",
                target_role=target_role,
                gap_count=len(gaps),
                overall_diff_score=overall_diff,
                candidate_skill_count=len(candidate_skills),
                correlation_id=context.correlation_id,
            )

            return {
                "role_profile": _serialise_role_profile(role_profile),
                "skill_gaps": [_serialise_gap(g) for g in gaps],
                "dimension_scores": {
                    "tech_skills": dimension_scores.tech_skills,
                    "soft_skills": dimension_scores.soft_skills,
                    "certifications": dimension_scores.certifications,
                    "portfolio": dimension_scores.portfolio,
                    "keywords": dimension_scores.keywords,
                },
                "overall_diff_score": overall_diff,
                "prioritised_gaps": [_serialise_gap(g) for g in prioritised],
                "processing_steps": [
                    "role_profiling",
                    "skill_gap_scoring",
                    "gap_prioritisation",
                ],
            }

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(
        self, context: AgentContext, step: str, description: str
    ) -> None:
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
                "gap_analysis.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Output serialisers ──────────────────────────────────────────────────────


def _compute_overall_diff(dim: DimensionScores) -> float:
    return round(
        dim.tech_skills * _DIM_WEIGHTS["tech_skills"]
        + dim.soft_skills * _DIM_WEIGHTS["soft_skills"]
        + dim.certifications * _DIM_WEIGHTS["certifications"]
        + dim.portfolio * _DIM_WEIGHTS["portfolio"]
        + dim.keywords * _DIM_WEIGHTS["keywords"],
        3,
    )


def _serialise_role_profile(profile: RoleProfile) -> dict:
    return {
        "role_title": profile.role_title,
        "typical_experience_months": profile.typical_experience_months,
        "keywords": profile.keywords,
        "requirements": [
            {
                "name": req.name,
                "dimension": req.dimension.value,
                "is_required": req.is_required,
                "description": req.description,
                "typical_level": req.typical_level,
            }
            for req in profile.requirements
        ],
    }


def _serialise_gap(gap: SkillGap) -> dict:
    return {
        "requirement_name": gap.requirement_name,
        "dimension": gap.dimension.value,
        "severity": gap.severity.value,
        "is_required": gap.is_required,
        "diff_score": gap.diff_score,
        "current_level": gap.current_level,
        "required_level": gap.required_level,
        "roi_score": gap.roi_score,
        "urgency_score": gap.urgency_score,
        "priority_rank": gap.priority_rank,
        "evidence": gap.evidence,
    }
