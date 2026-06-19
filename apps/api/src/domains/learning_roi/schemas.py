"""Learning ROI Tracker domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LearningType = Literal[
    "course", "book", "certification", "bootcamp", "degree", "article", "other"
]
LearningStatus = Literal["planned", "in_progress", "completed", "abandoned"]

_VALID_TYPES = ("course", "book", "certification", "bootcamp", "degree", "article", "other")
_VALID_STATUS = ("planned", "in_progress", "completed", "abandoned")


class LearningItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    type: LearningType = "course"
    provider: str = Field(default="", max_length=200)
    cost: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", max_length=8)
    hours: float = Field(default=0.0, ge=0)
    status: LearningStatus = "planned"
    skills: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default="", max_length=2000)
    link: str = Field(default="", max_length=1000)


class LearningItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    type: LearningType | None = None
    provider: str | None = Field(default=None, max_length=200)
    cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    hours: float | None = Field(default=None, ge=0)
    status: LearningStatus | None = None
    skills: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    link: str | None = Field(default=None, max_length=1000)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class LearningItemOut(BaseModel):
    id: str
    title: str
    type: LearningType
    provider: str
    cost: float
    currency: str
    hours: float
    status: LearningStatus
    skills: list[str]
    notes: str
    link: str
    # Computed (not persisted) — recomputed from current market signals on read.
    impact_score: int = 0
    relevance: float = 0.0
    roi_score: int = 0
    matched_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
    rank: int = 0
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "LearningItemOut":
        item_type = doc.get("type", "course")
        status = doc.get("status", "planned")
        return cls(
            id=doc.get("id", ""),
            title=doc.get("title", ""),
            type=item_type if item_type in _VALID_TYPES else "other",
            provider=doc.get("provider", ""),
            cost=float(doc.get("cost", 0) or 0),
            currency=doc.get("currency", "USD"),
            hours=float(doc.get("hours", 0) or 0),
            status=status if status in _VALID_STATUS else "planned",
            skills=list(doc.get("skills", []) or []),
            notes=doc.get("notes", ""),
            link=doc.get("link", ""),
            created_at=doc.get("created_at"),
        )


class LearningRoiSummary(BaseModel):
    """Portfolio-level rollup across all logged items."""

    total_items: int
    total_cost: float
    total_hours: float
    average_roi: int
    top_item_id: str | None = None
    has_market_signals: bool
