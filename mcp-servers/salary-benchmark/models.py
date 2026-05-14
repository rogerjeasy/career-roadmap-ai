"""Pydantic data models for the Salary Benchmark MCP server."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExperienceLevel(StrEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    UNKNOWN = "unknown"


class SalarySource(StrEnum):
    GLASSDOOR = "Glassdoor"
    LEVELS_FYI = "levels.fyi"
    CURATED = "curated_dataset"


class SalaryDataPoint(BaseModel):
    """A single salary observation."""

    source: SalarySource
    role: str
    location: str
    country: str
    experience_level: ExperienceLevel
    base_salary: int
    total_compensation: int | None = None
    currency: str = "CHF"
    year: int | None = None
    company: str | None = None


class SalaryRange(BaseModel):
    """Aggregated salary range for a role + level + location."""

    role: str
    country: str
    currency: str
    experience_level: ExperienceLevel

    p10: int | None = None
    p25: int | None = None
    median: int
    p75: int | None = None
    p90: int | None = None

    sample_count: int
    sources: list[SalarySource]
    fetched_at: str

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "country": self.country,
            "currency": self.currency,
            "experience_level": self.experience_level,
            "p10": self.p10,
            "p25": self.p25,
            "median": self.median,
            "p75": self.p75,
            "p90": self.p90,
            "sample_count": self.sample_count,
            "sources": [s.value for s in self.sources],
            "fetched_at": self.fetched_at,
        }


# ── Tool input / output schemas ────────────────────────────────────────────────


class GetSalaryRangeParams(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    country: str = Field(default="CH", min_length=2, max_length=2)
    experience_level: ExperienceLevel = ExperienceLevel.MID
    skills: list[str] = Field(default_factory=list, max_length=20)
    currency: str = Field(default="CHF", min_length=3, max_length=3)


class GetSalaryRangeResult(BaseModel):
    ranges: list[dict[str, Any]]
    role: str
    country: str
    total_sources: int
    fetched_at: str
