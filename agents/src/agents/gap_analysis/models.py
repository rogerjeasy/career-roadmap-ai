"""Gap Analysis domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GapSeverity(str, Enum):
    CRITICAL = "critical"   # Required skill — completely absent
    HIGH = "high"           # Required skill — partially present or low proficiency
    MEDIUM = "medium"       # Preferred skill — absent
    LOW = "low"             # Preferred skill — partially present


class GapDimension(str, Enum):
    TECH_SKILL = "tech_skill"
    SOFT_SKILL = "soft_skill"
    CERTIFICATION = "certification"
    PORTFOLIO = "portfolio"
    KEYWORD = "keyword"


@dataclass(frozen=True, slots=True)
class RoleRequirement:
    """A single requirement for the target role."""

    name: str
    dimension: GapDimension
    is_required: bool                     # True = must-have, False = nice-to-have
    description: str = ""
    typical_level: str | None = None      # beginner | intermediate | advanced | expert


@dataclass(frozen=True)
class RoleProfile:
    """Target role requirement profile built by RoleProfiler."""

    role_title: str
    requirements: list[RoleRequirement] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    typical_experience_months: int | None = None

    @property
    def required(self) -> list[RoleRequirement]:
        return [r for r in self.requirements if r.is_required]

    @property
    def preferred(self) -> list[RoleRequirement]:
        return [r for r in self.requirements if not r.is_required]

    @property
    def by_dimension(self) -> dict[str, list[RoleRequirement]]:
        result: dict[str, list[RoleRequirement]] = {}
        for req in self.requirements:
            result.setdefault(req.dimension.value, []).append(req)
        return result


@dataclass(frozen=True, slots=True)
class SkillGap:
    """A single identified gap between candidate profile and role requirement."""

    requirement_name: str
    dimension: GapDimension
    severity: GapSeverity
    is_required: bool
    diff_score: float           # 0-1: magnitude of the gap (0=no gap, 1=fully absent)
    current_level: str | None   # candidate's current proficiency (None = absent)
    required_level: str | None  # target proficiency for the role
    roi_score: float            # 0-1: expected return from closing this gap
    urgency_score: float        # 0-1: how urgently the gap needs to be closed
    priority_rank: int = 0      # 1-based rank assigned by GapPrioritiser (1 = highest)
    evidence: str = ""          # one-line rationale for this gap


@dataclass(frozen=True, slots=True)
class DimensionScores:
    """Aggregated gap score per dimension (0=no gap, 1=complete gap)."""

    tech_skills: float
    soft_skills: float
    certifications: float
    portfolio: float
    keywords: float


@dataclass(frozen=True)
class GapAnalysisResult:
    """Full gap analysis output produced by the pipeline."""

    role_profile: RoleProfile
    skill_gaps: list[SkillGap] = field(default_factory=list)
    dimension_scores: DimensionScores = field(
        default_factory=lambda: DimensionScores(0.0, 0.0, 0.0, 0.0, 0.0)
    )
    overall_diff_score: float = 0.0
    prioritised_gaps: list[SkillGap] = field(default_factory=list)
