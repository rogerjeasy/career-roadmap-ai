"""DriftDetector — pure computation: measure deviation from the active plan.

Stateless. Given weekly scorecards and the list of milestones that were
expected to be completed by now, it returns a DriftAnalysis that quantifies
how far the user has drifted from the plan.

Design: no I/O, no LLM calls — safe to use in unit tests with no mocks.
"""
from __future__ import annotations

from agents.core.logging import get_logger
from agents.progress.models import DriftAnalysis, DriftSeverity, WeeklyScorecard

logger = get_logger(__name__)

# drift_score thresholds (upper bounds for each severity band)
_THRESHOLD_ON_TRACK = 0.20
_THRESHOLD_MINOR = 0.40
_THRESHOLD_MODERATE = 0.65

# Weights for the drift score composite
_WEIGHT_COMPLETION = 0.65
_WEIGHT_HOURS = 0.35


class DriftDetector:
    """Analyse weekly scorecards and compute drift from the active plan."""

    def detect(
        self,
        scorecards: list[WeeklyScorecard],
        planned_milestones: list[str],
        *,
        correlation_id: str = "",
    ) -> DriftAnalysis:
        """Return a DriftAnalysis summarising plan deviation.

        Parameters
        ----------
        scorecards:
            Weekly self-reports ordered oldest → newest.
        planned_milestones:
            Names of milestones that should have been reached by now.
        """
        if not scorecards:
            return DriftAnalysis(
                drift_score=0.0,
                drift_severity=DriftSeverity.ON_TRACK,
                milestone_completion_rate=0.0,
                hours_variance=0.0,
                weeks_analysed=0,
                evidence="No scorecard data available yet.",
            )

        # All milestones completed across any scorecard
        completed_set: set[str] = set()
        for sc in scorecards:
            completed_set.update(sc.milestones_completed)

        # Milestone completion rate
        if planned_milestones:
            n_hit = sum(1 for m in planned_milestones if m in completed_set)
            milestone_completion_rate = n_hit / len(planned_milestones)
        else:
            milestone_completion_rate = 1.0

        # Hours variance (total actual − total planned across all scorecards)
        total_planned = sum(sc.planned_hours for sc in scorecards)
        total_spent = sum(sc.hours_spent for sc in scorecards)
        hours_variance = total_spent - total_planned

        # Normalised hours shortfall: how bad is the under-delivery relative to plan?
        if total_planned > 0:
            # Only penalise shortfall (under-delivery); over-delivery is fine
            shortfall_ratio = max(0.0, -hours_variance) / total_planned
            hours_score = min(shortfall_ratio, 1.0)
        else:
            hours_score = 0.0

        # Stalled milestones: planned but never completed
        stalled = [m for m in planned_milestones if m not in completed_set]

        # At-risk: planned in the *latest* scorecard but still open
        latest = scorecards[-1]
        at_risk = [m for m in latest.milestones_planned if m not in completed_set]

        # Composite drift score (bounded 0-1)
        completion_shortfall = 1.0 - milestone_completion_rate
        drift_score = round(
            completion_shortfall * _WEIGHT_COMPLETION + hours_score * _WEIGHT_HOURS,
            3,
        )
        drift_score = max(0.0, min(drift_score, 1.0))

        severity = _classify_severity(drift_score)

        # Collect recent blocker signals (last 4 weeks) for evidence string
        recent_blockers: list[str] = []
        for sc in scorecards[-4:]:
            recent_blockers.extend(sc.blockers)

        evidence = (
            f"Analysed {len(scorecards)} week(s): "
            f"{len(completed_set)} milestone(s) completed, "
            f"{len(stalled)} stalled. "
            f"Hours variance: {hours_variance:+.1f}h."
        )
        if recent_blockers:
            evidence += f" Recent blockers: {', '.join(recent_blockers[:3])}."

        logger.info(
            "drift_detector.completed",
            drift_score=drift_score,
            drift_severity=severity.value,
            milestone_completion_rate=milestone_completion_rate,
            stalled_count=len(stalled),
            weeks_analysed=len(scorecards),
            correlation_id=correlation_id,
        )

        return DriftAnalysis(
            drift_score=drift_score,
            drift_severity=severity,
            milestone_completion_rate=milestone_completion_rate,
            hours_variance=hours_variance,
            stalled_milestones=stalled,
            at_risk_milestones=at_risk,
            weeks_analysed=len(scorecards),
            evidence=evidence,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _classify_severity(drift_score: float) -> DriftSeverity:
    if drift_score < _THRESHOLD_ON_TRACK:
        return DriftSeverity.ON_TRACK
    if drift_score < _THRESHOLD_MINOR:
        return DriftSeverity.MINOR
    if drift_score < _THRESHOLD_MODERATE:
        return DriftSeverity.MODERATE
    return DriftSeverity.SEVERE
