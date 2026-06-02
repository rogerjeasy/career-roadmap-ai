"""Progress domain — weekly reviews and the career-health snapshot."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Weekly review ─────────────────────────────────────────────────────────────

class WeeklyReviewCreate(BaseModel):
    energy: int = Field(ge=1, le=5)
    focus: int = Field(ge=1, le=5)
    wins: str = Field(default="", max_length=4000)
    blockers: str = Field(default="", max_length=4000)
    week_of: str | None = Field(default=None, max_length=40)
    hours_invested: float = Field(default=0, ge=0, le=168)
    milestones_closed: int = Field(default=0, ge=0, le=100)


class WeeklyReviewOut(BaseModel):
    id: str
    energy: int
    focus: int
    wins: str
    blockers: str
    week_of: str | None
    hours_invested: float
    milestones_closed: int
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "WeeklyReviewOut":
        return cls(
            id=doc["id"],
            energy=int(doc.get("energy", 0)),
            focus=int(doc.get("focus", 0)),
            wins=doc.get("wins", ""),
            blockers=doc.get("blockers", ""),
            week_of=doc.get("week_of"),
            hours_invested=float(doc.get("hours_invested", 0) or 0),
            milestones_closed=int(doc.get("milestones_closed", 0) or 0),
            created_at=doc["created_at"],
        )


# ── Career-health snapshot ────────────────────────────────────────────────────

class HealthSignal(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    score: int = Field(ge=0, le=100)


class HealthSnapshotIn(BaseModel):
    score: int = Field(ge=0, le=100)
    delta: int | None = None
    signals: list[HealthSignal] = Field(default_factory=list)


class HealthSnapshotOut(BaseModel):
    score: int
    delta: int | None
    signals: list[HealthSignal]
    updated_at: datetime | None

    @classmethod
    def empty(cls) -> "HealthSnapshotOut":
        return cls(score=0, delta=None, signals=[], updated_at=None)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "HealthSnapshotOut":
        return cls(
            score=int(doc.get("score", 0)),
            delta=doc.get("delta"),
            signals=[
                HealthSignal(label=s.get("label", ""), score=int(s.get("score", 0)))
                for s in doc.get("signals", [])
                if isinstance(s, dict)
            ],
            updated_at=doc.get("updated_at"),
        )
