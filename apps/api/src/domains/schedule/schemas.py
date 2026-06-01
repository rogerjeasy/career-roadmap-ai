"""Schedule domain — habits and weekly time blocks."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

BlockCategory = Literal["build", "read", "network", "review"]


# ── Habits ────────────────────────────────────────────────────────────────────

class HabitCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    cadence: str = Field(default="Daily", max_length=80)


class HabitUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    cadence: str | None = Field(default=None, max_length=80)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class HabitOut(BaseModel):
    id: str
    label: str
    cadence: str
    streak: int
    done_today: bool
    created_at: datetime


# ── Weekly time blocks ────────────────────────────────────────────────────────

class ScheduleBlockCreate(BaseModel):
    day: int = Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")
    label: str = Field(min_length=1, max_length=200)
    category: BlockCategory = "build"


class ScheduleBlockOut(BaseModel):
    id: str
    day: int
    label: str
    category: BlockCategory
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ScheduleBlockOut":
        category = doc.get("category", "build")
        return cls(
            id=doc["id"],
            day=int(doc.get("day", 0)),
            label=doc.get("label", ""),
            category=category if category in ("build", "read", "network", "review") else "build",
            created_at=doc["created_at"],
        )
