"""Schedule domain — habits, weekly time blocks, and the weekly time budget."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

BlockCategory = Literal["build", "read", "network", "review"]
BudgetTone = Literal["green", "ink", "terra", "gold"]

# Display label + bar tone per category, mirrored by the frontend WeeklyBudgetBar.
CATEGORY_META: dict[BlockCategory, tuple[str, BudgetTone]] = {
    "build": ("Build", "green"),
    "read": ("Read", "ink"),
    "network": ("Network", "terra"),
    "review": ("Review", "gold"),
}


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
    # Recent completion history (ISO ``YYYY-MM-DD``), newest last, bounded.
    completed_dates: list[str] = Field(default_factory=list)
    # Completion flags for the current week, Monday … Sunday.
    week_completions: list[bool] = Field(default_factory=list)


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


# ── Weekly time budget ────────────────────────────────────────────────────────

def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class BudgetTargets(BaseModel):
    """Weekly target hours per category."""

    build: float = Field(default=0, ge=0, le=168)
    read: float = Field(default=0, ge=0, le=168)
    network: float = Field(default=0, ge=0, le=168)
    review: float = Field(default=0, ge=0, le=168)


class TimeLogCreate(BaseModel):
    category: BlockCategory = "build"
    hours: float = Field(gt=0, le=24)
    # Defaults to today (UTC) when omitted.
    logged_on: date | None = None


class TimeLogOut(BaseModel):
    id: str
    category: BlockCategory
    hours: float
    logged_on: date
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "TimeLogOut":
        category = doc.get("category", "build")
        return cls(
            id=doc["id"],
            category=category if category in ("build", "read", "network", "review") else "build",
            hours=float(doc.get("hours", 0) or 0),
            logged_on=_coerce_date(doc.get("logged_on")),
            created_at=doc["created_at"],
        )


class BudgetCategoryOut(BaseModel):
    id: BlockCategory
    label: str
    hours_logged: float
    hours_target: float
    tone: BudgetTone


class BudgetOut(BaseModel):
    # Monday of the current (UTC) week the logged hours are summed over.
    week_start: date
    categories: list[BudgetCategoryOut]
