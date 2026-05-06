"""ResourceEmbedder — groups ranked resources into roadmap phase embeddings.

Pure computation: no I/O, no LLM calls.

Phase assignment is driven by gap priority rank from GapAgent:
  Phase 1 — Foundation & Critical Gaps  : severity=critical OR priority_rank ≤ 3
  Phase 2 — Core Skill Development       : severity=high    OR priority_rank ≤ 7
  Phase 3 — Enhancement & Specialisation : remaining gaps
"""
from __future__ import annotations

from agents.core.logging import get_logger
from agents.learning_resources.models import (
    LearningResource,
    RoadmapPhaseEmbedding,
    SkillResourceBundle,
)

logger = get_logger(__name__)

_PHASE_BOUNDARIES = (3, 7)  # inclusive upper ranks for phases 1 and 2

_PHASE_META: dict[int, str] = {
    1: "Foundation & Critical Gaps",
    2: "Core Skill Development",
    3: "Enhancement & Specialisation",
}

_DEFAULT_HOURS_ESTIMATE = 20.0   # fallback when duration_hours is absent
_DEFAULT_RESOURCES_PER_PHASE = 5


class ResourceEmbedder:
    """Group resources into roadmap phase embeddings based on gap priority.

    Pure computation: no I/O, no LLM calls.

    Parameters
    ----------
    resources_per_phase:
        Maximum resources to include in each phase embedding.
    """

    def __init__(self, *, resources_per_phase: int = _DEFAULT_RESOURCES_PER_PHASE) -> None:
        self._resources_per_phase = resources_per_phase

    def embed(
        self,
        ranked_bundles: list[SkillResourceBundle],
    ) -> list[RoadmapPhaseEmbedding]:
        """Assign resources to roadmap phases.

        Parameters
        ----------
        ranked_bundles:
            Output of ResourceRanker — bundles sorted by gap_priority_rank.

        Returns
        -------
        List of RoadmapPhaseEmbeddings (up to 3), skipping empty phases.
        """
        phase_bundles: dict[int, list[SkillResourceBundle]] = {1: [], 2: [], 3: []}
        for bundle in ranked_bundles:
            phase = _assign_phase(bundle.gap_priority_rank, bundle.gap_severity)
            phase_bundles[phase].append(bundle)

        embeddings: list[RoadmapPhaseEmbedding] = []
        for phase_num in sorted(phase_bundles):
            bundles_in_phase = phase_bundles[phase_num]
            if not bundles_in_phase:
                continue

            phase_resources = _collect_top_resources(
                bundles_in_phase, limit=self._resources_per_phase
            )
            embeddings.append(
                RoadmapPhaseEmbedding(
                    phase_number=phase_num,
                    phase_title=_PHASE_META[phase_num],
                    skill_gaps=[b.skill_gap for b in bundles_in_phase],
                    resources=phase_resources,
                    estimated_hours=_estimate_hours(phase_resources),
                )
            )

        logger.debug(
            "resource_embedder.phases_produced",
            phase_count=len(embeddings),
        )
        return embeddings


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assign_phase(priority_rank: int, severity: str) -> int:
    if severity == "critical" or priority_rank <= _PHASE_BOUNDARIES[0]:
        return 1
    if severity == "high" or priority_rank <= _PHASE_BOUNDARIES[1]:
        return 2
    return 3


def _collect_top_resources(
    bundles: list[SkillResourceBundle],
    *,
    limit: int,
) -> list[LearningResource]:
    """Merge resources from all bundles in a phase, deduplicate, sort by overall_score."""
    seen: set[str] = set()
    merged: list[LearningResource] = []
    for bundle in bundles:
        for resource in bundle.resources:
            if resource.resource_id not in seen:
                seen.add(resource.resource_id)
                merged.append(resource)
    merged.sort(key=lambda r: r.overall_score, reverse=True)
    return merged[:limit]


def _estimate_hours(resources: list[LearningResource]) -> float:
    total = sum(
        r.duration_hours if r.duration_hours is not None else _DEFAULT_HOURS_ESTIMATE
        for r in resources
    )
    return round(total, 1)
