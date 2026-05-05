"""Opportunity agent data models.

Internal Pydantic models for opportunity input/output. Not imported outside
the opportunity package — callers interact via AgentResult.output (plain dict).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class JobListing(BaseModel):
    """A single job posting returned by the job-board MCP server."""

    id: str
    title: str
    company: str
    location: str
    description: str
    required_skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: str = ""
    url: str = ""
    remote: bool = False
    seniority_level: str | None = None  # junior | mid | senior | lead | principal


class JobMatchScore(BaseModel):
    """A job listing with computed fit scores and explanations."""

    listing: JobListing
    match_score: float = Field(ge=0.0, le=1.0)
    skill_overlap: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    salary_fit: bool | None = None
    location_fit: bool = True
    is_high_match: bool = False


class CVTailoringSnippet(BaseModel):
    """Tailored CV snippets for a specific job listing."""

    job_id: str
    job_title: str
    company: str
    summary_bullet: str = Field(description="One-line tailored professional summary")
    skill_highlights: list[str] = Field(
        default_factory=list,
        description="3-5 tailored achievement bullet points",
    )
    keywords_to_include: list[str] = Field(
        default_factory=list,
        description="ATS keywords to weave into the CV",
    )


class TargetCompany(BaseModel):
    """A company that appeared multiple times in high-match listings."""

    name: str
    reason: str
    job_count: int
    top_roles: list[str] = Field(default_factory=list)
    avg_match_score: float = Field(ge=0.0, le=1.0)


class OpportunityOutput(BaseModel):
    """Full output from one OpportunityAgent run."""

    total_listings_fetched: int
    scored_jobs: list[JobMatchScore] = Field(default_factory=list)
    high_match_jobs: list[JobMatchScore] = Field(default_factory=list)
    cv_tailoring: list[CVTailoringSnippet] = Field(default_factory=list)
    target_companies: list[TargetCompany] = Field(default_factory=list)
    match_alerts: list[str] = Field(default_factory=list)
    search_query: str = ""
    timestamp: str = ""
