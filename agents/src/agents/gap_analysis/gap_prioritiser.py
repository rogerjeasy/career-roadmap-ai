"""GapPrioritiser — rank identified gaps by ROI × urgency composite score.

Pure computation — no LLM call, no I/O. Always succeeds.

Ranking formula:
    composite = ROI_WEIGHT × roi_score
              + URGENCY_WEIGHT × (urgency_score × urgency_multiplier)
              + SEVERITY_BONUS[severity]

``urgency_multiplier`` slightly amplifies urgency when the user has a tight
timeline or high weekly hours available.
"""
from __future__ import annotations

from agents.core.logging import get_logger
from agents.gap_analysis.models import GapSeverity, SkillGap

logger = get_logger(__name__)

_ROI_WEIGHT = 0.45
_URGENCY_WEIGHT = 0.35
_SEVERITY_BONUS: dict[GapSeverity, float] = {
    GapSeverity.CRITICAL: 0.20,
    GapSeverity.HIGH: 0.12,
    GapSeverity.MEDIUM: 0.05,
    GapSeverity.LOW: 0.00,
}


class GapPrioritiser:
    """Assign priority ranks to a list of SkillGap objects.

    Stateless — can be shared across concurrent requests.
    """

    def prioritise(
        self,
        gaps: list[SkillGap],
        *,
        timeline_months: int | None = None,
        weekly_hours: int | None = None,
        correlation_id: str = "",
    ) -> list[SkillGap]:
        """Return gaps sorted by descending composite priority, rank set to 1-based index.

        ``timeline_months`` and ``weekly_hours`` boost urgency when the user
        faces time pressure or has capacity to close gaps quickly.
        """
        if not gaps:
            return []

        urgency_mult = _urgency_multiplier(timeline_months, weekly_hours)
        scored = sorted(
            gaps,
            key=lambda g: _composite(g, urgency_mult),
            reverse=True,
        )

        ranked = [
            SkillGap(
                requirement_name=g.requirement_name,
                dimension=g.dimension,
                severity=g.severity,
                is_required=g.is_required,
                diff_score=g.diff_score,
                current_level=g.current_level,
                required_level=g.required_level,
                roi_score=g.roi_score,
                urgency_score=g.urgency_score,
                priority_rank=rank + 1,
                evidence=g.evidence,
            )
            for rank, g in enumerate(scored)
        ]

        logger.info(
            "gap.prioritised",
            gap_count=len(ranked),
            top_gap=ranked[0].requirement_name,
            urgency_multiplier=urgency_mult,
            correlation_id=correlation_id,
        )
        return ranked


# ── Helpers ─────────────────────────────────────────────────────────────────


def _composite(gap: SkillGap, urgency_multiplier: float) -> float:
    return round(
        _ROI_WEIGHT * gap.roi_score
        + _URGENCY_WEIGHT * gap.urgency_score * urgency_multiplier
        + _SEVERITY_BONUS[gap.severity],
        4,
    )


def _urgency_multiplier(timeline_months: int | None, weekly_hours: int | None) -> float:
    multiplier = 1.0
    if timeline_months is not None and timeline_months <= 6:
        multiplier += 0.15   # tight deadline amplifies urgency
    if weekly_hours is not None and weekly_hours >= 20:
        multiplier += 0.10   # high capacity means more can be addressed urgently
    return min(multiplier, 1.30)
