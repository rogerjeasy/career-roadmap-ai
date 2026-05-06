"""CoachContextAssembler — builds the rich context bundle injected into the coach LLM prompt.

Reads from:
- AgentContext.user_profile (UserProfileSnapshot)
- AgentContext.user_profile.additional["conversation_history"]
- AgentContext.user_profile.additional["plan_context"]
- AgentContext.plan_snapshot (outputs of prior agents in same run)

Returns a CoachContextBundle that the CoachAgent turns into a structured LLM prompt.
"""
from __future__ import annotations

from typing import Any

from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.coach.models import CoachContextBundle

logger = get_logger(__name__)

# Max history turns to include to stay within token budget
_MAX_HISTORY_TURNS = 12


class CoachContextAssembler:
    """Stateless context assembler — safe to call concurrently."""

    def assemble(self, context: AgentContext) -> CoachContextBundle:
        """Build a CoachContextBundle from all available context sources."""
        profile = context.user_profile
        additional = dict(profile.additional)

        conversation_history = _extract_history(additional)
        plan_ctx = additional.get("plan_context", {})
        plan_snapshot = context.plan_snapshot

        roadmap_summary = _extract_roadmap_summary(plan_ctx, plan_snapshot)
        gap_summary = _extract_gap_summary(plan_snapshot)
        market_summary = _extract_market_summary(plan_snapshot)
        progress_summary = _extract_progress_summary(plan_snapshot)

        has_plan = bool(roadmap_summary)

        logger.info(
            "coach.context_assembled",
            has_plan=has_plan,
            history_turns=len(conversation_history),
            has_gap=bool(gap_summary),
            has_market=bool(market_summary),
            correlation_id=context.correlation_id,
        )

        return CoachContextBundle(
            user_message=context.user_message,
            current_role=profile.current_role,
            target_role=profile.target_role,
            skills=list(profile.skills),
            goals=list(profile.goals),
            constraints=list(profile.constraints),
            timeline_months=profile.timeline_months,
            weekly_hours=profile.weekly_hours_available,
            conversation_history=conversation_history,
            roadmap_summary=roadmap_summary,
            gap_summary=gap_summary,
            market_summary=market_summary,
            progress_summary=progress_summary,
            has_plan=has_plan,
        )


# ── Private helpers ────────────────────────────────────────────────────────────


def _extract_history(additional: dict[str, Any]) -> list[dict[str, Any]]:
    raw = additional.get("conversation_history", [])
    if not isinstance(raw, list):
        return []
    turns = []
    for turn in raw[-_MAX_HISTORY_TURNS:]:
        if isinstance(turn, dict) and "role" in turn and "content" in turn:
            turns.append({"role": str(turn["role"]), "content": str(turn["content"])})
    return turns


def _extract_roadmap_summary(
    plan_ctx: dict[str, Any], plan_snapshot: dict[str, Any]
) -> str | None:
    # Prefer live plan_snapshot (from a concurrent roadmap agent run)
    roadmap = plan_snapshot.get("roadmap_generation") or {}
    if roadmap:
        phases = roadmap.get("phases", [])
        if phases:
            phase_names = [p.get("name", f"Phase {i+1}") for i, p in enumerate(phases)]
            total_weeks = roadmap.get("total_weeks") or roadmap.get("duration_weeks")
            lines = [f"Generated roadmap: {len(phases)} phases — {', '.join(phase_names)}."]
            if total_weeks:
                lines.append(f"Total duration: {total_weeks} weeks.")
            if milestones := roadmap.get("milestones", []):
                lines.append(f"Key milestones: {len(milestones)} defined.")
            return " ".join(lines)

    # Fall back to cached plan context from session
    snapshot = plan_ctx.get("snapshot", {}) if isinstance(plan_ctx, dict) else {}
    if snapshot:
        return f"User has a saved roadmap (snapshot available, roadmap_id: {plan_ctx.get('roadmap_id', 'unknown')})."

    return None


def _extract_gap_summary(plan_snapshot: dict[str, Any]) -> str | None:
    gap = plan_snapshot.get("gap_analysis") or {}
    if not gap:
        return None
    lines = []
    if diff_score := gap.get("diff_score"):
        lines.append(f"Skill readiness score: {diff_score:.0%}.")
    if critical := gap.get("critical_gaps", []):
        lines.append(f"Critical gaps: {', '.join(str(g) for g in critical[:5])}.")
    if priorities := gap.get("priority_order", []):
        lines.append(f"Priority learning order: {', '.join(str(p) for p in priorities[:5])}.")
    return " ".join(lines) if lines else None


def _extract_market_summary(plan_snapshot: dict[str, Any]) -> str | None:
    market = plan_snapshot.get("market_intelligence") or {}
    if not market:
        return None
    summary = market.get("summary") or market.get("narrative")
    if summary:
        return str(summary)[:600]
    return None


def _extract_progress_summary(plan_snapshot: dict[str, Any]) -> str | None:
    progress = plan_snapshot.get("progress") or {}
    if not progress:
        return None
    lines = []
    if drift := progress.get("drift_detected"):
        lines.append(f"Plan drift detected: {drift}.")
    if habits := progress.get("habit_summary"):
        lines.append(f"Habits: {str(habits)[:200]}.")
    return " ".join(lines) if lines else None
