"""Pydantic data models for the Job Board MCP server.

These are the canonical data shapes that all clients and tools use.
No ORM coupling — pure Pydantic v2.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobSource(StrEnum):
    LINKEDIN = "LinkedIn"
    INDEED = "Indeed"
    GLASSDOOR = "Glassdoor"
    SWISS_JOBS = "jobs.ch"
    JOBUP = "jobup.ch"
    ADZUNA = "Adzuna"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    UNKNOWN = "unknown"


class ExperienceLevel(StrEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class JobPosting(BaseModel):
    """A normalised job posting from any source."""

    id: str = Field(description="Source-specific job ID or URL hash")
    title: str
    company: str
    location: str
    country: str = Field(default="", description="ISO 3166-1 alpha-2 country code")
    remote: bool = False
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN
    description: str = Field(default="", description="Full job description (may be truncated)")
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    salary_min: int | None = Field(default=None, description="Annual min salary in local currency")
    salary_max: int | None = Field(default=None, description="Annual max salary in local currency")
    currency: str = "USD"
    source: JobSource = JobSource.UNKNOWN
    source_url: str | None = None
    posted_date: date | None = None
    apply_url: str | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("required_skills", "nice_to_have_skills", mode="before")
    @classmethod
    def deduplicate_skills(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        for s in v:
            norm = str(s).strip()
            if norm and norm.lower() not in seen:
                seen.add(norm.lower())
                result.append(norm)
        return result

    def model_dump_api(self) -> dict[str, Any]:
        """Serialise to the dict shape the agent's JobBoardFetcher expects."""
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "country": self.country,
            "remote": self.remote,
            "employment_type": self.employment_type,
            "experience_level": self.experience_level,
            "required_skills": self.required_skills,
            "nice_to_have_skills": self.nice_to_have_skills,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "currency": self.currency,
            "source": self.source,
            "url": self.source_url,
            "apply_url": self.apply_url,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "fetched_at": self.fetched_at.isoformat(),
        }


class TrendingRole(BaseModel):
    """A role that is trending in the job market."""

    title: str
    posting_count: int
    growth_percent: float | None = Field(default=None, description="Week-over-week posting growth % (None when source lacks historical data)")
    top_skills: list[str]
    median_salary: int | None = None
    currency: str = "USD"
    country: str
    sources: list[JobSource] = Field(default_factory=list)


# ── Tool input / output schemas ───────────────────────────────────────────────


class SearchJobsParams(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    country: str = Field(default="CH", min_length=2, max_length=2)
    location: str | None = None
    remote: bool | None = None
    skills: list[str] = Field(default_factory=list, max_length=20)
    experience_level: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None
    salary_min: int | None = None
    limit: int = Field(default=20, ge=1, le=50)
    sources: list[JobSource] = Field(default_factory=list)


class SearchJobsResult(BaseModel):
    postings: list[dict[str, Any]]
    total_count: int
    sources_queried: list[str]
    fetched_at: str


class GetJobDetailParams(BaseModel):
    job_id: str = Field(min_length=1)
    source: JobSource
    country: str = Field(default="CH", min_length=2, max_length=2)


class GetTrendingRolesParams(BaseModel):
    country: str = Field(default="CH", min_length=2, max_length=2)
    category: str | None = Field(default=None, description="Industry category filter")
    limit: int = Field(default=10, ge=1, le=25)
