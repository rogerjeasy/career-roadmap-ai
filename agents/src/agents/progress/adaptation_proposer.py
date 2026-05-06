"""AdaptationProposer — LLM-based plan adaptation proposals.

Given drift analysis, habit streaks, and the current plan snapshot, this
component asks the LLM for structured adaptation proposals. It falls back
to rule-based heuristics when all LLM retries are exhausted.

Design: stateless, injectable LLM client, OTel + Prometheus observability.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import (
    PROGRESS_ADAPT_DURATION,
    PROGRESS_ADAPT_TOTAL,
    get_tracer,
)
from agents.progress.models import (
    AdaptationChange,
    AdaptationProposal,
    AdaptationType,
    DriftAnalysis,
    DriftSeverity,
    HabitStreak,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.progress.adaptation_proposer")

_SYSTEM_PROMPT = """\
You are a career coach reviewing a user's weekly progress data and proposing \
targeted, actionable adaptations to their career roadmap.
Return ONLY valid JSON (no markdown fences):
{
  "adaptations": [
    {
      "adaptation_type": "pace_adjustment|milestone_reorder|scope_reduction|resource_swap|habit_reset|full_regeneration",
      "trigger_reason": "<one sentence explaining why this adaptation is needed>",
      "confidence": 0.0-1.0,
      "requires_regeneration": true|false,
      "summary": "<one-sentence summary of the adaptation>",
      "changes": [
        {
          "change_type": "pace|remove|swap|defer|reset",
          "target": "<milestone or habit or resource name>",
          "description": "<what to change>",
          "rationale": "<why this change helps>",
          "priority": 1-5
        }
      ]
    }
  ]
}

Guidelines:
- Propose at most 3 adaptations. Fewer is better if the drift is low.
- on_track severity  → 0-1 minor optimisations (improvement only).
- minor severity     → 1-2 pace adjustments or habit resets.
- moderate severity  → 2-3 changes including possible scope reduction.
- severe severity    → scope_reduction and/or full_regeneration.
- Set requires_regeneration=true only when drift_score > 0.70 or stalled milestones > 3.
- confidence reflects certainty given the available data (0=guess, 1=very confident).
- Keep changes concrete: name the specific milestone, habit, or resource to change.
"""


class AdaptationProposer:
    """Propose plan adaptations based on drift analysis and habit streaks.

    Inject a custom ``llm`` in tests to avoid real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.2,
        )

    async def propose(
        self,
        drift: DriftAnalysis,
        habit_streaks: list[HabitStreak],
        plan_snapshot: dict[str, Any],
        user_profile_summary: str,
        *,
        correlation_id: str = "",
    ) -> list[AdaptationProposal]:
        """Return adaptation proposals for the given drift state."""
        with _tracer.start_as_current_span("progress.propose_adaptations") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("drift_score", drift.drift_score)
            span.set_attribute("drift_severity", drift.drift_severity.value)
            t0 = time.monotonic()

            try:
                proposals = await self._propose_with_llm(
                    drift, habit_streaks, plan_snapshot, user_profile_summary, correlation_id
                )
                PROGRESS_ADAPT_TOTAL.labels(status="llm").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "progress.adapt_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    drift_score=drift.drift_score,
                    correlation_id=correlation_id,
                )
                proposals = _heuristic_proposals(drift, habit_streaks)
                PROGRESS_ADAPT_TOTAL.labels(status="fallback").inc()

            duration = time.monotonic() - t0
            PROGRESS_ADAPT_DURATION.observe(duration)
            span.set_attribute("proposal_count", len(proposals))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "progress.adaptations_proposed",
                proposal_count=len(proposals),
                drift_severity=drift.drift_severity.value,
                requires_regeneration=any(p.requires_regeneration for p in proposals),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return proposals

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _propose_with_llm(
        self,
        drift: DriftAnalysis,
        habit_streaks: list[HabitStreak],
        plan_snapshot: dict[str, Any],
        user_profile_summary: str,
        correlation_id: str,
    ) -> list[AdaptationProposal]:
        context_msg = _build_context_message(
            drift, habit_streaks, plan_snapshot, user_profile_summary
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=context_msg),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return _build_proposals(raw)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_context_message(
    drift: DriftAnalysis,
    habit_streaks: list[HabitStreak],
    plan_snapshot: dict[str, Any],
    user_profile_summary: str,
) -> str:
    stalled_txt = ", ".join(drift.stalled_milestones[:5]) or "none"
    at_risk_txt = ", ".join(drift.at_risk_milestones[:5]) or "none"

    low_habits = [h.habit_name for h in habit_streaks if h.completion_rate < 0.5]
    broken_habits_txt = ", ".join(low_habits[:5]) or "none"

    target_role = plan_snapshot.get("target_role", "the target role")

    return (
        f"User profile: {user_profile_summary}\n"
        f"Target role: {target_role}\n\n"
        f"Drift analysis:\n"
        f"  drift_score: {drift.drift_score:.2f} ({drift.drift_severity.value})\n"
        f"  milestone_completion_rate: {drift.milestone_completion_rate:.0%}\n"
        f"  hours_variance: {drift.hours_variance:+.1f}h\n"
        f"  weeks_analysed: {drift.weeks_analysed}\n"
        f"  stalled_milestones: {stalled_txt}\n"
        f"  at_risk_milestones: {at_risk_txt}\n"
        f"  evidence: {drift.evidence}\n\n"
        f"Habits with <50% completion rate: {broken_habits_txt}\n\n"
        "Propose the minimum set of adaptations to bring the plan back on track."
    )


def _build_proposals(raw: dict[str, Any]) -> list[AdaptationProposal]:
    proposals: list[AdaptationProposal] = []
    for item in raw.get("adaptations", []):
        if not isinstance(item, dict):
            continue
        try:
            a_type = AdaptationType(item.get("adaptation_type", "pace_adjustment"))
        except ValueError:
            a_type = AdaptationType.PACE_ADJUSTMENT

        changes: list[AdaptationChange] = []
        for c in item.get("changes", []):
            if not isinstance(c, dict) or not c.get("target"):
                continue
            changes.append(
                AdaptationChange(
                    change_type=str(c.get("change_type", "pace")),
                    target=str(c["target"]),
                    description=str(c.get("description", "")),
                    rationale=str(c.get("rationale", "")),
                    priority=int(c.get("priority", 1)),
                )
            )

        proposals.append(
            AdaptationProposal(
                adaptation_type=a_type,
                trigger_reason=str(item.get("trigger_reason", "")),
                changes=changes,
                confidence=float(max(0.0, min(1.0, item.get("confidence", 0.5)))),
                requires_regeneration=bool(item.get("requires_regeneration", False)),
                summary=str(item.get("summary", "")),
            )
        )
    return proposals


def _heuristic_proposals(
    drift: DriftAnalysis,
    habit_streaks: list[HabitStreak],
) -> list[AdaptationProposal]:
    """Rule-based fallback when LLM is unavailable."""
    proposals: list[AdaptationProposal] = []

    if drift.drift_severity == DriftSeverity.ON_TRACK:
        return proposals

    # Pace adjustment for minor/moderate drift
    if drift.drift_severity in {DriftSeverity.MINOR, DriftSeverity.MODERATE}:
        changes: list[AdaptationChange] = []
        if drift.stalled_milestones:
            changes.append(
                AdaptationChange(
                    change_type="defer",
                    target=drift.stalled_milestones[0],
                    description="Defer this stalled milestone to next week.",
                    rationale="Progress data shows consistent shortfall on this milestone.",
                    priority=1,
                )
            )
        proposals.append(
            AdaptationProposal(
                adaptation_type=AdaptationType.PACE_ADJUSTMENT,
                trigger_reason=(
                    f"Drift score {drift.drift_score:.2f} indicates plan-reality gap."
                ),
                changes=changes,
                confidence=0.6,
                requires_regeneration=False,
                summary="Reduce weekly milestone target to align with actual capacity.",
            )
        )

    # Habit reset for persistently broken habits
    broken = [h for h in habit_streaks if h.completion_rate < 0.4]
    if broken:
        proposals.append(
            AdaptationProposal(
                adaptation_type=AdaptationType.HABIT_RESET,
                trigger_reason=f"{len(broken)} habit(s) with <40% completion rate.",
                changes=[
                    AdaptationChange(
                        change_type="reset",
                        target=h.habit_name,
                        description="Reset habit cadence to a lighter schedule.",
                        rationale="Low completion rate suggests current target is too demanding.",
                        priority=2,
                    )
                    for h in broken[:2]
                ],
                confidence=0.7,
                requires_regeneration=False,
                summary="Reset underperforming habits to rebuild consistency.",
            )
        )

    # Full regeneration for severe drift or many stalled milestones
    if drift.drift_severity == DriftSeverity.SEVERE or len(drift.stalled_milestones) > 3:
        proposals.append(
            AdaptationProposal(
                adaptation_type=AdaptationType.FULL_REGENERATION,
                trigger_reason=(
                    f"Severe drift (score={drift.drift_score:.2f}) requires full re-planning."
                ),
                changes=[],
                confidence=0.8,
                requires_regeneration=True,
                summary="Re-generate the roadmap with updated timeline and capacity.",
            )
        )

    return proposals
