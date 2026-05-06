"""ResourceRanker — ranks learning resources by quality, cost, level fit, and relevance.

Scoring formula (weights must sum to 1.0):
  overall_score = 0.35 × relevance_score
                + 0.30 × quality_score
                + 0.20 × cost_value_score   (free = 1.0, degrades with price)
                + 0.15 × level_fit_score    (level matches the gap's severity)

Pure computation: no I/O, no LLM calls.
"""
from __future__ import annotations

from agents.core.logging import get_logger
from agents.learning_resources.models import LearningResource, ResourceLevel, SkillResourceBundle

logger = get_logger(__name__)

# Ranking weights — must sum to 1.0
_W_RELEVANCE: float = 0.35
_W_QUALITY: float = 0.30
_W_COST_VALUE: float = 0.20
_W_LEVEL_FIT: float = 0.15

# Global top resources surfaced in the agent output
_TOP_GLOBAL = 10


class ResourceRanker:
    """Apply weighted ranking to all SkillResourceBundles.

    Pure computation: no I/O, no LLM calls.

    Parameters
    ----------
    top_global:
        How many overall top resources to surface across all gaps.
    """

    def __init__(self, *, top_global: int = _TOP_GLOBAL) -> None:
        self._top_global = top_global

    def rank(
        self,
        bundles: list[SkillResourceBundle],
    ) -> tuple[list[SkillResourceBundle], list[LearningResource]]:
        """Score and rank resources within each bundle.

        Returns
        -------
        ranked_bundles:
            Input bundles with resources replaced by scored + sorted versions.
        top_resources:
            Global top-k resources across all bundles by overall_score.
        """
        all_resources: list[LearningResource] = []
        ranked_bundles: list[SkillResourceBundle] = []

        for bundle in bundles:
            scored = [
                _score_resource(r, bundle.gap_severity)
                for r in bundle.resources
            ]
            scored.sort(key=lambda r: r.overall_score, reverse=True)
            ranked_bundles.append(
                SkillResourceBundle(
                    skill_gap=bundle.skill_gap,
                    gap_severity=bundle.gap_severity,
                    gap_priority_rank=bundle.gap_priority_rank,
                    resources=scored,
                )
            )
            all_resources.extend(scored)

        # Global top-k: deduplicate by resource_id, sort by overall_score
        seen: set[str] = set()
        unique: list[LearningResource] = []
        for r in sorted(all_resources, key=lambda x: x.overall_score, reverse=True):
            if r.resource_id not in seen:
                seen.add(r.resource_id)
                unique.append(r)

        return ranked_bundles, unique[: self._top_global]


# ── Scoring helpers ───────────────────────────────────────────────────────────


def _score_resource(resource: LearningResource, gap_severity: str) -> LearningResource:
    """Return a new LearningResource with overall_score computed."""
    cost_val = _cost_value_score(resource.cost_usd)
    level_val = _level_fit_score(resource.level, gap_severity)

    overall = round(
        _W_RELEVANCE * resource.relevance_score
        + _W_QUALITY * resource.quality_score
        + _W_COST_VALUE * cost_val
        + _W_LEVEL_FIT * level_val,
        3,
    )

    return LearningResource(
        resource_id=resource.resource_id,
        title=resource.title,
        provider=resource.provider,
        skill_tags=resource.skill_tags,
        level=resource.level,
        format=resource.format,
        duration_hours=resource.duration_hours,
        cost_usd=resource.cost_usd,
        quality_score=resource.quality_score,
        relevance_score=resource.relevance_score,
        overall_score=overall,
        is_free=resource.is_free,
        url=resource.url,
        description=resource.description,
        freshness_year=resource.freshness_year,
        source=resource.source,
    )


def _cost_value_score(cost_usd: float) -> float:
    """Score cost-effectiveness (free = 1.0, expensive = lower)."""
    if cost_usd == 0.0:
        return 1.0
    if cost_usd <= 20.0:
        return 0.85
    if cost_usd <= 50.0:
        return 0.70
    if cost_usd <= 100.0:
        return 0.55
    return 0.40


# (gap_severity, resource_level) → level-fit score
_LEVEL_FIT: dict[tuple[str, ResourceLevel], float] = {
    ("critical", ResourceLevel.BEGINNER): 0.95,
    ("critical", ResourceLevel.INTERMEDIATE): 0.80,
    ("critical", ResourceLevel.ADVANCED): 0.55,
    ("critical", ResourceLevel.EXPERT): 0.40,
    ("high", ResourceLevel.BEGINNER): 0.70,
    ("high", ResourceLevel.INTERMEDIATE): 1.00,
    ("high", ResourceLevel.ADVANCED): 0.85,
    ("high", ResourceLevel.EXPERT): 0.60,
    ("medium", ResourceLevel.BEGINNER): 0.55,
    ("medium", ResourceLevel.INTERMEDIATE): 0.85,
    ("medium", ResourceLevel.ADVANCED): 1.00,
    ("medium", ResourceLevel.EXPERT): 0.90,
    ("low", ResourceLevel.BEGINNER): 0.50,
    ("low", ResourceLevel.INTERMEDIATE): 0.75,
    ("low", ResourceLevel.ADVANCED): 0.95,
    ("low", ResourceLevel.EXPERT): 1.00,
}


def _level_fit_score(level: ResourceLevel, gap_severity: str) -> float:
    return _LEVEL_FIT.get((gap_severity, level), 0.70)
