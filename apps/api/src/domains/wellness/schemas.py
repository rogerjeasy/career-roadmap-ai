"""Wellness & Sustainability Monitor domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WellnessCheckinCreate(BaseModel):
    energy: int = Field(ge=1, le=5)
    stress: int = Field(ge=1, le=5)
    motivation: int = Field(ge=1, le=5)
    hours_worked: float = Field(default=40.0, ge=0, le=168)
    sleep_hours: float = Field(default=7.0, ge=0, le=24)
    notes: str = Field(default="", max_length=1000)


class WellnessCheckinOut(BaseModel):
    id: str
    energy: int
    stress: int
    motivation: int
    hours_worked: float
    sleep_hours: float
    notes: str
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "WellnessCheckinOut":
        return cls(
            id=doc.get("id", ""),
            energy=int(doc.get("energy", 3) or 3),
            stress=int(doc.get("stress", 3) or 3),
            motivation=int(doc.get("motivation", 3) or 3),
            hours_worked=float(doc.get("hours_worked", 40) or 40),
            sleep_hours=float(doc.get("sleep_hours", 7) or 7),
            notes=doc.get("notes", ""),
            created_at=doc.get("created_at"),
        )


class WellnessStatus(BaseModel):
    risk_score: int
    risk_level: str
    trend: str
    drivers: list[str]
    recommendation: str
    recovery_suggested: bool
    sample_size: int
