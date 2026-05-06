"""Learning Resources domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ResourceLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ResourceFormat(str, Enum):
    COURSE = "course"
    VIDEO = "video"
    BOOK = "book"
    ARTICLE = "article"
    PROJECT = "project"
    WORKSHOP = "workshop"
    CERTIFICATION = "certification"


@dataclass(frozen=True)
class LearningResource:
    """A single learning resource matched and ranked for a skill gap."""

    resource_id: str
    title: str
    provider: str                      # Coursera, Udemy, edX, YouTube, O'Reilly …
    skill_tags: list[str]              # normalised lowercase skill keywords
    level: ResourceLevel
    format: ResourceFormat
    duration_hours: float | None
    cost_usd: float                    # 0.0 = free
    quality_score: float               # 0–1 provider reputation × review aggregate
    relevance_score: float             # 0–1 computed by ResourceMatcher
    overall_score: float               # 0–1 weighted final ranking score
    is_free: bool
    url: str | None = None
    description: str = ""
    freshness_year: int | None = None  # year of last content update
    source: str = "mcp_course_catalog"


@dataclass(frozen=True)
class SkillResourceBundle:
    """Top resources matched to a single skill gap."""

    skill_gap: str
    gap_severity: str       # critical | high | medium | low
    gap_priority_rank: int  # 1 = highest priority (from GapAgent)
    resources: list[LearningResource]

    @property
    def top_resource(self) -> LearningResource | None:
        return self.resources[0] if self.resources else None


@dataclass(frozen=True)
class RoadmapPhaseEmbedding:
    """Resources grouped for a single roadmap learning phase."""

    phase_number: int
    phase_title: str
    skill_gaps: list[str]
    resources: list[LearningResource]
    estimated_hours: float


@dataclass
class LearningResourcesResult:
    """Full output produced by the Learning Resources pipeline."""

    target_role: str
    skill_recommendations: list[SkillResourceBundle] = field(default_factory=list)
    top_resources: list[LearningResource] = field(default_factory=list)
    roadmap_embeddings: list[RoadmapPhaseEmbedding] = field(default_factory=list)
    total_resources_found: int = 0
    total_learning_hours: float = 0.0
    data_sources: list[str] = field(default_factory=list)
    processing_steps: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
