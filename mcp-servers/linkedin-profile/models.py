"""Pydantic models for the LinkedIn Profile MCP server."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class ConnectionDegree(str, Enum):
    FIRST = "1st"
    SECOND = "2nd"
    THIRD = "3rd+"


# ── LinkedIn Profile ──────────────────────────────────────────────────────────

class LinkedInExperience(BaseModel):
    title: str
    company: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None

    def model_dump_api(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=False)


class LinkedInEducation(BaseModel):
    school: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class LinkedInProfile(BaseModel):
    id: str
    full_name: str
    headline: str | None = None
    summary: str | None = None
    location: str | None = None
    profile_url: str
    avatar_url: str | None = None
    connections: int | None = None
    followers: int | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[LinkedInExperience] = Field(default_factory=list)
    education: list[LinkedInEducation] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    source: str = "LinkedIn"

    def model_dump_api(self) -> dict[str, Any]:
        return {
            **self.model_dump(exclude={"experiences", "education"}),
            "experiences": [e.model_dump_api() for e in self.experiences],
            "education": [ed.model_dump() for ed in self.education],
        }


# ── Job Title Normalisation ───────────────────────────────────────────────────

class NormalizedJobTitle(BaseModel):
    raw_title: str
    canonical_title: str
    seniority_level: str | None = None  # "junior" | "mid" | "senior" | "lead" | "principal" | "staff" | "manager" | "director" | "vp" | "c-level"
    role_family: str | None = None      # "engineering" | "data" | "product" | "design" | "management" | "sales" | "marketing" | "operations"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: str = "rules"


# ── Connection Suggestion ─────────────────────────────────────────────────────

class ConnectionSuggestion(BaseModel):
    id: str
    full_name: str
    headline: str | None = None
    location: str | None = None
    profile_url: str
    avatar_url: str | None = None
    connection_degree: ConnectionDegree = ConnectionDegree.SECOND
    shared_skills: list[str] = Field(default_factory=list)
    relevance_score: float = Field(ge=0.0, le=1.0, default=0.5)
    reason: str = ""
    source: str = "LinkedIn"


# ── Request params ────────────────────────────────────────────────────────────

class FetchProfileParams(BaseModel):
    profile_url: str = Field(description="LinkedIn profile URL or public identifier")
    access_token: str | None = Field(
        default=None,
        description="OAuth2 bearer token for user-consented access (optional for public profiles)",
    )


class NormalizeJobTitleParams(BaseModel):
    raw_title: str = Field(description="Raw job title string to normalise", max_length=200)
    industry: str | None = Field(default=None, description="Optional industry context")


class SuggestConnectionsParams(BaseModel):
    skills: list[str] = Field(description="Target skills to match against connections")
    target_role: str = Field(description="Target job role for the user")
    location: str | None = Field(default=None, description="Optional location filter")
    limit: int = Field(default=10, ge=1, le=50)
    access_token: str = Field(description="OAuth2 bearer token for LinkedIn People Search")
