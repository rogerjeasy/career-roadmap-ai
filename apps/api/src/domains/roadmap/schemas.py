"""Roadmap domain — Pydantic schemas for Firestore storage and HTTP responses."""
from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic cursor-based paginated response envelope."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


# ── Embedded sub-models ───────────────────────────────────────────────────────

class SkillItem(BaseModel):
    """A skill with priority flag — shown in phase skill cards."""
    text: str
    is_priority: bool = False
    display_order: int = 0


class ActionItem(BaseModel):
    """A concrete action step with supporting context."""
    text: str
    sub_text: str = ""
    display_order: int = 0


class LearningResource(BaseModel):
    """A curated learning resource linked to a phase."""
    title: str
    resource_type: str = "tutorial"
    provider: str = ""
    difficulty: str = "intermediate"
    tags: list[str] = Field(default_factory=list)
    url: str | None = None
    estimated_hours: float | None = None
    is_free: bool = True
    description: str = ""


class WeeklyTask(BaseModel):
    """One week's actionable work items within a phase."""
    week_number: int
    focus_area: str = ""
    tasks: list[str] = Field(default_factory=list)
    estimated_hours: float = 0.0
    deliverable: str | None = None


# ── Internal domain models (storage ↔ service layer) ─────────────────────────

class RoadmapPhase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    title: str
    description: str = ""
    duration_weeks: int
    goals: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    skills_to_gain: list[str] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    gaps_addressed: list[str] = Field(default_factory=list)
    market_relevance: str = ""
    difficulty: str = "intermediate"
    deliverables: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    resources: list[LearningResource] = Field(default_factory=list)
    curated_resources: list[LearningResource] = Field(default_factory=list)
    weekly_tasks: list[WeeklyTask] = Field(default_factory=list)


class WeeklyHabit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    text: str
    frequency: str = "daily"
    duration_minutes: int = 0
    rationale: str = ""


class NextStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    action: str


class RoadmapDocument(BaseModel):
    """Full roadmap including all subcollection data loaded from Firestore."""
    id: str
    user_id: str
    session_id: str
    request_id: str
    summary: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str
    validation_passed: bool = True
    unverified_claims: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    market_grounding: dict = Field(default_factory=dict)
    phases: list[RoadmapPhase] = Field(default_factory=list)
    weekly_habits: list[WeeklyHabit] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
    created_at: datetime
    deleted_at: datetime | None = None


class RoadmapSummary(BaseModel):
    """Lightweight projection for list views — subcollections are not loaded."""
    id: str
    user_id: str
    session_id: str
    request_id: str
    summary: str
    confidence: float
    status: str
    phase_count: int = 0
    created_at: datetime
    deleted_at: datetime | None = None


# ── HTTP response schemas (snake_case → camelCase via CaseConversionMiddleware) ─

class SkillItemOut(BaseModel):
    text: str
    is_priority: bool
    display_order: int


class ActionItemOut(BaseModel):
    text: str
    sub_text: str
    display_order: int


class LearningResourceOut(BaseModel):
    title: str
    resource_type: str
    provider: str
    difficulty: str
    tags: list[str]
    url: str | None
    estimated_hours: float | None
    is_free: bool
    description: str


class WeeklyTaskOut(BaseModel):
    week_number: int
    focus_area: str
    tasks: list[str]
    estimated_hours: float
    deliverable: str | None


class RoadmapPhaseOut(BaseModel):
    id: str
    order: int
    title: str
    description: str
    duration_weeks: int
    goals: list[str]
    milestones: list[str]
    skills_to_gain: list[str]
    skills: list[SkillItemOut]
    actions: list[ActionItemOut]
    gaps_addressed: list[str]
    market_relevance: str
    difficulty: str
    deliverables: list[str]
    confidence: float
    resources: list[LearningResourceOut]
    curated_resources: list[LearningResourceOut]
    weekly_tasks: list[WeeklyTaskOut]


class WeeklyHabitOut(BaseModel):
    order: int
    text: str
    frequency: str
    duration_minutes: int
    rationale: str


class RoadmapOut(BaseModel):
    """Full roadmap response — returned by GET /roadmaps/{id}."""
    id: str
    session_id: str
    summary: str
    confidence: float
    status: str
    validation_passed: bool
    unverified_claims: list[str]
    duration_ms: int
    market_grounding: dict
    phases: list[RoadmapPhaseOut]
    weekly_habits: list[WeeklyHabitOut]
    next_steps: list[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, doc: RoadmapDocument) -> "RoadmapOut":
        return cls(
            id=doc.id,
            session_id=doc.session_id,
            summary=doc.summary,
            confidence=doc.confidence,
            status=doc.status,
            validation_passed=doc.validation_passed,
            unverified_claims=doc.unverified_claims,
            duration_ms=doc.duration_ms,
            market_grounding=doc.market_grounding,
            phases=[
                RoadmapPhaseOut(
                    id=p.id,
                    order=p.order,
                    title=p.title,
                    description=p.description,
                    duration_weeks=p.duration_weeks,
                    goals=p.goals,
                    milestones=p.milestones,
                    skills_to_gain=p.skills_to_gain,
                    skills=[
                        SkillItemOut(
                            text=s.text,
                            is_priority=s.is_priority,
                            display_order=s.display_order,
                        )
                        for s in p.skills
                    ],
                    actions=[
                        ActionItemOut(
                            text=a.text,
                            sub_text=a.sub_text,
                            display_order=a.display_order,
                        )
                        for a in p.actions
                    ],
                    gaps_addressed=p.gaps_addressed,
                    market_relevance=p.market_relevance,
                    difficulty=p.difficulty,
                    deliverables=p.deliverables,
                    confidence=p.confidence,
                    resources=[
                        LearningResourceOut(
                            title=r.title,
                            resource_type=r.resource_type,
                            provider=r.provider,
                            difficulty=r.difficulty,
                            tags=r.tags,
                            url=r.url,
                            estimated_hours=r.estimated_hours,
                            is_free=r.is_free,
                            description=r.description,
                        )
                        for r in p.resources
                    ],
                    curated_resources=[
                        LearningResourceOut(
                            title=r.title,
                            resource_type=r.resource_type,
                            provider=r.provider,
                            difficulty=r.difficulty,
                            tags=r.tags,
                            url=r.url,
                            estimated_hours=r.estimated_hours,
                            is_free=r.is_free,
                            description=r.description,
                        )
                        for r in p.curated_resources
                    ],
                    weekly_tasks=[
                        WeeklyTaskOut(
                            week_number=t.week_number,
                            focus_area=t.focus_area,
                            tasks=t.tasks,
                            estimated_hours=t.estimated_hours,
                            deliverable=t.deliverable,
                        )
                        for t in p.weekly_tasks
                    ],
                )
                for p in sorted(doc.phases, key=lambda p: p.order)
            ],
            weekly_habits=[
                WeeklyHabitOut(
                    order=h.order,
                    text=h.text,
                    frequency=h.frequency,
                    duration_minutes=h.duration_minutes,
                    rationale=h.rationale,
                )
                for h in sorted(doc.weekly_habits, key=lambda h: h.order)
            ],
            next_steps=[s.action for s in sorted(doc.next_steps, key=lambda s: s.order)],
            created_at=doc.created_at,
        )


class RoadmapSummaryOut(BaseModel):
    """Compact roadmap response — returned by GET /roadmaps."""
    id: str
    session_id: str
    summary: str
    confidence: float
    status: str
    phase_count: int
    created_at: datetime

    @classmethod
    def from_domain(cls, summary: RoadmapSummary) -> "RoadmapSummaryOut":
        return cls(
            id=summary.id,
            session_id=summary.session_id,
            summary=summary.summary,
            confidence=summary.confidence,
            status=summary.status,
            phase_count=summary.phase_count,
            created_at=summary.created_at,
        )


# Paginated list response — returned by GET /roadmaps?cursor=...&limit=...
RoadmapSummaryPage = PaginatedResponse[RoadmapSummaryOut]
