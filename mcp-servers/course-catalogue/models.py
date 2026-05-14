"""Pydantic data models for the Course Catalogue MCP server.

These are the canonical data shapes that all clients and tools use.
No ORM coupling — pure Pydantic v2.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CourseSource(StrEnum):
    COURSERA = "Coursera"
    UDEMY = "Udemy"
    EDX = "edX"
    YOUTUBE = "YouTube"
    OREILLY = "O'Reilly"
    FREE_RESOURCES = "Free Resources"
    UNKNOWN = "unknown"


class SkillLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ALL = "all"


class Course(BaseModel):
    """A normalised course record from any platform."""

    id: str = Field(description="Source-specific course ID or URL hash")
    title: str
    platform: CourseSource = CourseSource.UNKNOWN
    instructor: str = Field(default="", description="Instructor or channel name")
    url: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    skill_level: SkillLevel = SkillLevel.ALL
    duration_hours: float | None = Field(default=None, description="Estimated hours to complete")
    rating: float | None = Field(default=None, ge=0, le=5)
    num_ratings: int | None = None
    price: float | None = Field(default=None, description="Course price; None = unknown or free")
    currency: str = "USD"
    free: bool = False
    language: str = "en"
    certificate: bool = False
    thumbnail_url: str | None = None
    published_date: date | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("skills", mode="before")
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
        """Serialise to the dict shape expected by agents."""
        return {
            "id": self.id,
            "title": self.title,
            "platform": self.platform,
            "instructor": self.instructor,
            "url": self.url,
            "description": self.description[:1000],
            "skills": self.skills,
            "skill_level": self.skill_level,
            "duration_hours": self.duration_hours,
            "rating": self.rating,
            "num_ratings": self.num_ratings,
            "price": self.price,
            "currency": self.currency,
            "free": self.free,
            "language": self.language,
            "certificate": self.certificate,
            "thumbnail_url": self.thumbnail_url,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "fetched_at": self.fetched_at.isoformat(),
        }


# ── Tool input / output schemas ───────────────────────────────────────────────


class SearchCoursesParams(BaseModel):
    skill: str = Field(min_length=1, max_length=200, description="Skill or topic to search for")
    level: SkillLevel = SkillLevel.ALL
    language: str = Field(default="en", min_length=2, max_length=5)
    free_only: bool = False
    limit: int = Field(default=20, ge=1, le=50)
    sources: list[CourseSource] = Field(default_factory=list)


class SearchCoursesResult(BaseModel):
    courses: list[dict[str, Any]]
    total_count: int
    sources_queried: list[str]
    fetched_at: str


class GetCourseDetailParams(BaseModel):
    course_id: str = Field(min_length=1)
    source: CourseSource
