"""Roadmap Generation domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ResourceType(str, Enum):
    COURSE = "course"
    BOOK = "book"
    TUTORIAL = "tutorial"
    DOCUMENTATION = "documentation"
    PROJECT = "project"
    CERTIFICATION = "certification"
    COMMUNITY = "community"
    VIDEO = "video"


@dataclass(frozen=True)
class SkillItem:
    """A skill with priority flag and ordering — shown in phase skill cards."""

    text: str
    is_priority: bool = False
    display_order: int = 0


@dataclass(frozen=True)
class ActionItem:
    """A concrete action step with supporting context — shown as ordered action list."""

    text: str
    sub_text: str = ""
    display_order: int = 0


@dataclass(frozen=True)
class Resource:
    """A curated learning resource linked to one or more skills."""

    title: str
    resource_type: ResourceType
    provider: str
    difficulty: DifficultyLevel
    tags: list[str]
    url: str | None = None
    estimated_hours: float | None = None
    is_free: bool = True
    description: str = ""
    phase_index: int = 0


@dataclass(frozen=True)
class WeeklyTask:
    """Actionable work items for a single calendar week."""

    week_number: int
    phase_index: int
    focus_area: str
    tasks: list[str]
    estimated_hours: float
    deliverable: str | None = None


@dataclass(frozen=True)
class Habit:
    """A recurring practice habit to sustain throughout the roadmap."""

    name: str
    frequency: str  # "daily" | "weekly"
    duration_minutes: int
    rationale: str
    phase_start: int = 1


@dataclass(frozen=True)
class Milestone:
    """A measurable checkpoint at the end of a learning phase."""

    name: str
    description: str
    phase_index: int
    week_number: int
    success_criteria: list[str]
    skills_demonstrated: list[str]
    deliverable: str
    icon: str = "🎯"


@dataclass(frozen=True)
class Phase:
    """One sequential learning phase in the roadmap."""

    index: int
    title: str
    description: str
    duration_weeks: int
    goals: list[str]
    skills_to_acquire: list[str]          # flat list kept for backward compat + resource linking
    skills: list[SkillItem] = field(default_factory=list)   # structured, with is_priority
    actions: list[ActionItem] = field(default_factory=list) # concrete steps with sub_text
    gaps_addressed: list[str] = field(default_factory=list)
    market_relevance: str = ""
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER


@dataclass(frozen=True)
class RoadmapResult:
    """Full roadmap output produced by the RoadmapAgent pipeline."""

    role: str
    timeline_months: int
    summary: str = ""
    market_grounding: dict = field(default_factory=dict)
    processing_steps: list[str] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    weekly_schedule: list[WeeklyTask] = field(default_factory=list)
    habits: list[Habit] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    roadmap_id: str = field(default_factory=lambda: str(uuid4()))
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
