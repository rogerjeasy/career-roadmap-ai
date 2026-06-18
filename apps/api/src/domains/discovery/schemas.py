"""Discovery domain — Pydantic schemas.

The career-discovery flow turns a CV/profile (with no fixed target) into a set
of comparable ``CareerPathOption`` objects — each with a fit score, effort to
switch, salary band, growth outlook, the key skills to gain, and a sample
multi-phase roadmap — so the user can weigh paths side by side and convert one
into an active plan.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EffortLevel = Literal["low", "medium", "high"]


class SamplePhase(BaseModel):
    title: str
    duration_weeks: int = 0
    focus: str = ""


class CareerPathOption(BaseModel):
    title: str
    summary: str = ""
    fit_score: int = Field(default=0, ge=0, le=100)
    effort_to_switch: EffortLevel = "medium"
    timeline_months: int = 0
    salary_currency: str = ""
    salary_low: int = 0
    salary_high: int = 0
    growth_outlook: str = ""
    key_skills_to_gain: list[str] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    sample_phases: list[SamplePhase] = Field(default_factory=list)
    rationale: str = ""


class DiscoveryResult(BaseModel):
    paths: list[CareerPathOption] = Field(default_factory=list)
    based_on: str = ""  # short note on what the paths were derived from
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    has_data: bool = False
    generated_at: datetime | None = None

    @classmethod
    def empty(cls) -> "DiscoveryResult":
        return cls(paths=[], has_data=False)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "DiscoveryResult":
        paths = [
            CareerPathOption.model_validate(p)
            for p in doc.get("paths", [])
            if isinstance(p, dict)
        ]
        return cls(
            paths=paths,
            based_on=doc.get("based_on", ""),
            confidence=float(doc.get("confidence", 0.5) or 0.5),
            has_data=bool(paths),
            generated_at=doc.get("generated_at") or doc.get("created_at"),
        )
