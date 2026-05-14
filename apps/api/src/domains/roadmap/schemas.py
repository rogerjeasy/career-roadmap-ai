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


# ── Internal domain models (storage ↔ service layer) ─────────────────────────

class RoadmapPhase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    title: str
    duration_weeks: int
    milestones: list[str] = Field(default_factory=list)
    skills_to_gain: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WeeklyHabit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int
    text: str


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

class RoadmapPhaseOut(BaseModel):
    id: str
    order: int
    title: str
    duration_weeks: int
    milestones: list[str]
    skills_to_gain: list[str]
    confidence: float


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
    phases: list[RoadmapPhaseOut]
    weekly_habits: list[str]
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
            phases=[
                RoadmapPhaseOut(
                    id=p.id,
                    order=p.order,
                    title=p.title,
                    duration_weeks=p.duration_weeks,
                    milestones=p.milestones,
                    skills_to_gain=p.skills_to_gain,
                    confidence=p.confidence,
                )
                for p in sorted(doc.phases, key=lambda p: p.order)
            ],
            weekly_habits=[h.text for h in sorted(doc.weekly_habits, key=lambda h: h.order)],
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
