"""ResourceMatcher — maps raw course results to skill gaps with relevance scoring.

Pure computation: no I/O, no LLM calls.
Relevance is a Jaccard-like overlap between the gap's keyword tokens
and the course's skill_tag tokens.
"""
from __future__ import annotations

import re
from typing import Any

from agents.core.logging import get_logger
from agents.learning_resources.models import (
    LearningResource,
    ResourceFormat,
    ResourceLevel,
    SkillResourceBundle,
)

logger = get_logger(__name__)

_TOP_K_PER_GAP = 5   # keep at most this many resources per gap after matching

_LEVEL_MAP: dict[str, ResourceLevel] = {
    "beginner": ResourceLevel.BEGINNER,
    "intermediate": ResourceLevel.INTERMEDIATE,
    "advanced": ResourceLevel.ADVANCED,
    "expert": ResourceLevel.EXPERT,
}

_FORMAT_MAP: dict[str, ResourceFormat] = {
    "course": ResourceFormat.COURSE,
    "video": ResourceFormat.VIDEO,
    "book": ResourceFormat.BOOK,
    "article": ResourceFormat.ARTICLE,
    "project": ResourceFormat.PROJECT,
    "workshop": ResourceFormat.WORKSHOP,
    "certification": ResourceFormat.CERTIFICATION,
}


class ResourceMatcher:
    """Match raw course dicts to skill gap bundles and compute relevance scores.

    Parameters
    ----------
    top_k:
        Maximum resources to retain per skill gap after relevance filtering.
    """

    def __init__(self, *, top_k: int = _TOP_K_PER_GAP) -> None:
        self._top_k = top_k

    def match(
        self,
        gaps: list[dict[str, Any]],
        raw_courses: dict[str, list[dict[str, Any]]],
    ) -> list[SkillResourceBundle]:
        """Match and score courses for each gap.

        Parameters
        ----------
        gaps:
            Serialised gap dicts from GapAgent (prioritised_gaps).
        raw_courses:
            Dict mapping requirement_name → list of raw course dicts from CourseFetcher.

        Returns
        -------
        list of SkillResourceBundles sorted by gap_priority_rank (ascending).
        """
        bundles: list[SkillResourceBundle] = []

        for gap in gaps:
            skill_name = gap["requirement_name"]
            courses_raw = raw_courses.get(skill_name, [])
            gap_keywords = _tokenise(skill_name)

            resources: list[LearningResource] = []
            for raw in courses_raw:
                relevance = _compute_relevance(gap_keywords, raw.get("skill_tags", []))
                resources.append(_build_resource(raw, relevance_score=relevance))

            # Sort by relevance; ResourceRanker will apply full weighted scoring later.
            resources.sort(key=lambda r: r.relevance_score, reverse=True)
            resources = resources[: self._top_k]

            bundles.append(
                SkillResourceBundle(
                    skill_gap=skill_name,
                    gap_severity=gap.get("severity", "high"),
                    gap_priority_rank=gap.get("priority_rank", 999),
                    resources=resources,
                )
            )

        bundles.sort(key=lambda b: b.gap_priority_rank)
        return bundles


# ── Helpers ───────────────────────────────────────────────────────────────────


def _tokenise(text: str) -> frozenset[str]:
    """Tokenise and normalise a skill name or tag into keyword atoms."""
    tokens = re.split(r"[\s\-_/+.,]+", text.lower())
    return frozenset(t for t in tokens if len(t) > 1)


def _compute_relevance(gap_keywords: frozenset[str], skill_tags: list[str]) -> float:
    """Jaccard similarity between gap keywords and course skill_tags."""
    if not gap_keywords:
        return 0.5

    tag_keywords: frozenset[str] = frozenset()
    for tag in skill_tags:
        tag_keywords = tag_keywords | _tokenise(tag)

    if not tag_keywords:
        return 0.5

    intersection = gap_keywords & tag_keywords
    union = gap_keywords | tag_keywords
    return round(len(intersection) / len(union), 3) if union else 0.0


def _build_resource(raw: dict[str, Any], *, relevance_score: float) -> LearningResource:
    """Construct a LearningResource from a raw MCP course dict."""
    cost = float(raw.get("cost_usd", 0.0))
    return LearningResource(
        resource_id=str(raw.get("id", "")),
        title=str(raw.get("title", "Unknown")),
        provider=str(raw.get("provider", "Unknown")),
        skill_tags=list(raw.get("skill_tags", [])),
        level=_LEVEL_MAP.get(str(raw.get("level", "")), ResourceLevel.INTERMEDIATE),
        format=_FORMAT_MAP.get(str(raw.get("format", "")), ResourceFormat.COURSE),
        duration_hours=raw.get("duration_hours"),
        cost_usd=cost,
        quality_score=float(raw.get("quality_score", 0.70)),
        relevance_score=relevance_score,
        overall_score=0.0,   # filled by ResourceRanker
        is_free=cost == 0.0,
        url=raw.get("url"),
        description=str(raw.get("description", "")),
        freshness_year=raw.get("freshness_year"),
        source=str(raw.get("source", "mcp_course_catalog")),
    )
