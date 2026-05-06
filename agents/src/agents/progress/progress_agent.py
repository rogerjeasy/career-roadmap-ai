"""ProgressAgent — L3 Specialist Agent: progress tracking and plan adaptation.

Three-step pipeline:
  1. Drift Detection     (DriftDetector)        — pure computation: measure plan deviation
  2. Habit Analysis      (HabitStreakAnalyser)  — pure computation: streak + completion rates
  3. Adaptation Proposals (AdaptationProposer)  — LLM: propose targeted plan changes

Input (via context.plan_snapshot):
  plan_snapshot["scorecards"]          : list[dict] — weekly scorecard history
  plan_snapshot["planned_milestones"]  : list[str]  — milestones expected by now
  plan_snapshot["target_role"]         : str        — target role for LLM context
  plan_snapshot["active_plan"]         : dict       — full plan context (optional)

Output (AgentResult.output):
  drift_analysis       : dict   — drift score, severity, stalled milestones, evidence
  habit_streaks        : list   — per-habit streak and completion data
  adaptations          : list   — proposed plan changes with type, changes, confidence
  requires_regeneration: bool   — whether full re-generation is warranted
  analysis_summary     : str    — paragraph summary of the analysis
  processing_steps     : list[str]

Low-coupled: all three components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each step so the client shows live progress.

Registration (at Celery worker startup):
    from agents.progress import ProgressAgent
    from agents.core.agent_registry import registry
    registry.register(ProgressAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

from datetime import date

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    PROGRESS_ADAPT_COUNT,
    PROGRESS_DRIFT_SCORE,
    PROGRESS_REGEN_TOTAL,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.progress.adaptation_proposer import AdaptationProposer
from agents.progress.drift_detector import DriftDetector
from agents.progress.habit_streak_analyser import HabitStreakAnalyser
from agents.progress.models import (
    AdaptationProposal,
    DriftAnalysis,
    HabitStreak,
    WeeklyScorecard,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.progress.progress_agent")


class ProgressAgent(BaseAgent):
    """Track weekly progress, detect drift, and propose roadmap adaptations.

    Parameters
    ----------
    drift_detector:
        Pure-computation drift analyser. Defaults to ``DriftDetector()``.
    habit_streak_analyser:
        Pure-computation habit streak computer. Defaults to ``HabitStreakAnalyser()``.
    adaptation_proposer:
        LLM-based adaptation proposer. Defaults to ``AdaptationProposer()``.
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events. When ``None``
        progress events are silently skipped (e.g. in unit tests).
    llm:
        Override LLM forwarded to LLM-dependent components when not explicitly provided.
    """

    def __init__(
        self,
        *,
        drift_detector: DriftDetector | None = None,
        habit_streak_analyser: HabitStreakAnalyser | None = None,
        adaptation_proposer: AdaptationProposer | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._drift_detector = drift_detector or DriftDetector()
        self._habit_streak_analyser = habit_streak_analyser or HabitStreakAnalyser()
        self._adaptation_proposer = adaptation_proposer or AdaptationProposer(llm=llm)
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.PROGRESS

    @property
    def display_name(self) -> str:
        return "Progress & Adaptation Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full progress analysis and adaptation pipeline."""
        with _tracer.start_as_current_span("progress.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            raw_scorecards: list[dict] = context.plan_snapshot.get("scorecards", [])
            planned_milestones: list[str] = context.plan_snapshot.get(
                "planned_milestones", []
            )
            # Active plan dict forwarded to the LLM for context
            active_plan: dict = context.plan_snapshot.get(
                "active_plan", context.plan_snapshot
            )

            scorecards = _parse_scorecards(raw_scorecards)
            span.set_attribute("scorecard_count", len(scorecards))
            span.set_attribute("planned_milestone_count", len(planned_milestones))

            # ── Step 1: Drift detection ────────────────────────────────────
            self._emit_progress(
                context,
                "drift_detection",
                "Analysing weekly progress and detecting drift from plan…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="progress.drift_detection").inc()

            drift: DriftAnalysis = self._drift_detector.detect(
                scorecards,
                planned_milestones,
                correlation_id=context.correlation_id,
            )

            PROGRESS_DRIFT_SCORE.observe(drift.drift_score)
            span.set_attribute("drift_score", drift.drift_score)
            span.set_attribute("drift_severity", drift.drift_severity.value)

            # ── Step 2: Habit streak analysis ──────────────────────────────
            self._emit_progress(
                context,
                "habit_analysis",
                "Computing habit streaks and completion rates…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="progress.habit_analysis").inc()

            habit_streaks: list[HabitStreak] = self._habit_streak_analyser.analyse(
                scorecards,
                correlation_id=context.correlation_id,
            )
            span.set_attribute("habit_count", len(habit_streaks))

            # ── Step 3: Adaptation proposals ───────────────────────────────
            self._emit_progress(
                context,
                "adaptation_proposals",
                "Generating plan adaptation proposals…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="progress.adaptation_proposals").inc()

            user_profile_summary = _build_profile_summary(context)
            adaptations: list[AdaptationProposal] = (
                await self._adaptation_proposer.propose(
                    drift,
                    habit_streaks,
                    active_plan,
                    user_profile_summary,
                    correlation_id=context.correlation_id,
                )
            )

            requires_regeneration = any(p.requires_regeneration for p in adaptations)
            PROGRESS_ADAPT_COUNT.observe(len(adaptations))
            if requires_regeneration:
                PROGRESS_REGEN_TOTAL.inc()

            span.set_attribute("adaptation_count", len(adaptations))
            span.set_attribute("requires_regeneration", requires_regeneration)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "progress.analysis_completed",
                drift_score=drift.drift_score,
                drift_severity=drift.drift_severity.value,
                habit_count=len(habit_streaks),
                adaptation_count=len(adaptations),
                requires_regeneration=requires_regeneration,
                scorecard_count=len(scorecards),
                correlation_id=context.correlation_id,
            )

            return {
                "drift_analysis": _serialise_drift(drift),
                "habit_streaks": [_serialise_habit_streak(h) for h in habit_streaks],
                "adaptations": [_serialise_adaptation(a) for a in adaptations],
                "requires_regeneration": requires_regeneration,
                "analysis_summary": _build_summary(drift, habit_streaks, adaptations),
                "processing_steps": [
                    "drift_detection",
                    "habit_analysis",
                    "adaptation_proposals",
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
                "progress.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Serialisers ──────────────────────────────────────────────────────────────


def _serialise_drift(drift: DriftAnalysis) -> dict:
    return {
        "drift_score": drift.drift_score,
        "drift_severity": drift.drift_severity.value,
        "milestone_completion_rate": drift.milestone_completion_rate,
        "hours_variance": drift.hours_variance,
        "stalled_milestones": drift.stalled_milestones,
        "at_risk_milestones": drift.at_risk_milestones,
        "weeks_analysed": drift.weeks_analysed,
        "evidence": drift.evidence,
    }


def _serialise_habit_streak(h: HabitStreak) -> dict:
    return {
        "habit_name": h.habit_name,
        "current_streak_weeks": h.current_streak_weeks,
        "longest_streak_weeks": h.longest_streak_weeks,
        "completion_rate": h.completion_rate,
        "total_weeks_tracked": h.total_weeks_tracked,
        "weeks_completed": h.weeks_completed,
    }


def _serialise_adaptation(a: AdaptationProposal) -> dict:
    return {
        "adaptation_type": a.adaptation_type.value,
        "trigger_reason": a.trigger_reason,
        "confidence": a.confidence,
        "requires_regeneration": a.requires_regeneration,
        "summary": a.summary,
        "changes": [
            {
                "change_type": c.change_type,
                "target": c.target,
                "description": c.description,
                "rationale": c.rationale,
                "priority": c.priority,
            }
            for c in a.changes
        ],
    }


# ── Input parsers ─────────────────────────────────────────────────────────────


def _parse_scorecards(raw_list: list[dict]) -> list[WeeklyScorecard]:
    """Convert raw dicts from plan_snapshot to typed WeeklyScorecard objects."""
    result: list[WeeklyScorecard] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue

        week_start = item.get("week_start_date")
        if isinstance(week_start, str):
            try:
                week_start = date.fromisoformat(week_start)
            except ValueError:
                week_start = date.today()
        elif not isinstance(week_start, date):
            week_start = date.today()

        result.append(
            WeeklyScorecard(
                week_start_date=week_start,
                milestones_planned=list(item.get("milestones_planned", [])),
                milestones_completed=list(item.get("milestones_completed", [])),
                habit_completions={
                    k: bool(v)
                    for k, v in item.get("habit_completions", {}).items()
                },
                hours_spent=float(item.get("hours_spent", 0.0)),
                planned_hours=float(item.get("planned_hours", 0.0)),
                notes=str(item.get("notes", "")),
                blockers=list(item.get("blockers", [])),
            )
        )

    return sorted(result, key=lambda s: s.week_start_date)


def _build_profile_summary(context: AgentContext) -> str:
    p = context.user_profile
    parts: list[str] = []
    if p.target_role:
        parts.append(f"Target: {p.target_role}")
    if p.current_role:
        parts.append(f"Current: {p.current_role}")
    if p.timeline_months:
        parts.append(f"Timeline: {p.timeline_months} months")
    if p.weekly_hours_available:
        parts.append(f"Weekly capacity: {p.weekly_hours_available}h")
    return ", ".join(parts) or "No profile context"


def _build_summary(
    drift: DriftAnalysis,
    habit_streaks: list[HabitStreak],
    adaptations: list[AdaptationProposal],
) -> str:
    low_habits = [h for h in habit_streaks if h.completion_rate < 0.5]
    regen = any(p.requires_regeneration for p in adaptations)

    parts: list[str] = [
        f"Drift: {drift.drift_severity.value} "
        f"(score={drift.drift_score:.2f}, {drift.weeks_analysed} week(s) analysed).",
    ]
    if drift.stalled_milestones:
        names = ", ".join(drift.stalled_milestones[:3])
        parts.append(f"{len(drift.stalled_milestones)} stalled milestone(s): {names}.")
    if low_habits:
        names = ", ".join(h.habit_name for h in low_habits[:3])
        parts.append(f"{len(low_habits)} habit(s) below 50% completion: {names}.")
    if adaptations:
        types = ", ".join(a.adaptation_type.value for a in adaptations)
        parts.append(f"Proposed {len(adaptations)} adaptation(s): {types}.")
    if regen:
        parts.append("Full roadmap regeneration recommended.")

    return " ".join(parts)
