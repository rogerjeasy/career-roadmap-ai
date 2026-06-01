"""Monthly plan domain — monthly themes with weekly goal breakdowns."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PlanStatus = Literal["done", "current", "future"]


class WeekGoal(BaseModel):
    week: int = Field(ge=1, le=6)
    focus: str = Field(default="", max_length=200)
    goals: list[str] = Field(default_factory=list)


class MonthlyPlanUpsert(BaseModel):
    month_id: str = Field(min_length=1, max_length=20, description="e.g. '2026-06'")
    month: str = Field(min_length=1, max_length=60, description="e.g. 'June 2026'")
    theme: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=2000)
    status: PlanStatus = "future"
    weeks: list[WeekGoal] = Field(default_factory=list)
    goals_total: int = Field(default=0, ge=0)
    goals_done: int = Field(default=0, ge=0)


class MonthlyPlanOut(BaseModel):
    id: str
    month_id: str
    month: str
    theme: str
    summary: str
    status: PlanStatus
    weeks: list[WeekGoal]
    goals_total: int
    goals_done: int
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MonthlyPlanOut":
        status = doc.get("status", "future")
        return cls(
            id=doc["id"],
            month_id=doc.get("month_id", ""),
            month=doc.get("month", ""),
            theme=doc.get("theme", ""),
            summary=doc.get("summary", ""),
            status=status if status in ("done", "current", "future") else "future",
            weeks=[
                WeekGoal(
                    week=int(w.get("week", 1)),
                    focus=w.get("focus", ""),
                    goals=list(w.get("goals", [])),
                )
                for w in doc.get("weeks", [])
                if isinstance(w, dict)
            ],
            goals_total=int(doc.get("goals_total", 0)),
            goals_done=int(doc.get("goals_done", 0)),
            created_at=doc["created_at"],
        )


class MonthlyPlanSummaryOut(BaseModel):
    id: str
    month_id: str
    month: str
    theme: str
    status: PlanStatus
    goals_total: int
    goals_done: int

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MonthlyPlanSummaryOut":
        status = doc.get("status", "future")
        return cls(
            id=doc["id"],
            month_id=doc.get("month_id", ""),
            month=doc.get("month", ""),
            theme=doc.get("theme", ""),
            status=status if status in ("done", "current", "future") else "future",
            goals_total=int(doc.get("goals_total", 0)),
            goals_done=int(doc.get("goals_done", 0)),
        )
