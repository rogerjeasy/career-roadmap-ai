"""Pydantic data models for the Social Signals MCP server.

No ORM coupling — pure Pydantic v2. All clients normalise their
source-specific payloads into ``SocialSignal`` before returning.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SocialSource(StrEnum):
    HACKERNEWS = "HackerNews"
    REDDIT = "Reddit"
    TWITTER = "Twitter/X"
    DEVTO = "Dev.to"
    UNKNOWN = "unknown"


class SocialSignal(BaseModel):
    """A normalised social signal from any source."""

    id: str = Field(description="Source-specific post/tweet/article ID")
    title: str
    url: str
    source: SocialSource = SocialSource.UNKNOWN
    score: int = Field(default=0, description="Upvotes, points, or likes")
    comment_count: int = Field(default=0)
    author: str = Field(default="")
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(
        default_factory=list,
        description="Tech keywords matched from the search query",
    )
    summary: str = Field(default="", description="Short description or text snippet")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("tags", "tech_stack", mode="before")
    @classmethod
    def deduplicate_list(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        for item in v:
            norm = str(item).strip().lower()
            if norm and norm not in seen:
                seen.add(norm)
                result.append(str(item).strip())
        return result

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "score": self.score,
            "comment_count": self.comment_count,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tags": self.tags,
            "tech_stack": self.tech_stack,
            "summary": self.summary,
            "fetched_at": self.fetched_at.isoformat(),
        }


class TrendingTopic(BaseModel):
    """A tech topic that is trending across social platforms."""

    topic: str = Field(description="The trending technology or concept")
    stack: str = Field(description="Primary tech stack category (e.g., Python, React)")
    signal_count: int = Field(description="Number of matching signals found")
    total_score: int = Field(description="Sum of all signal scores (upvotes/points)")
    sources: list[SocialSource] = Field(default_factory=list)
    top_signals: list[dict[str, Any]] = Field(
        default_factory=list, description="Up to 3 representative signals"
    )


# ── Tool parameter models ─────────────────────────────────────────────────────


class GetHackerNewsSignalsParams(BaseModel):
    stacks: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Tech stacks to search for (e.g., ['Python', 'FastAPI'])",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="HN tags filter: story, ask_hn, show_hn, job (default: story)",
    )
    min_score: int = Field(default=10, ge=0, description="Minimum points threshold")
    limit: int = Field(default=10, ge=1, le=30)


class GetRedditSignalsParams(BaseModel):
    stacks: list[str] = Field(min_length=1, max_length=10)
    subreddits: list[str] = Field(
        default_factory=list,
        description="Override subreddit list; auto-selected from stack if empty",
    )
    time_filter: str = Field(
        default="week",
        description="Reddit time filter: hour, day, week, month, year, all",
    )
    sort: str = Field(
        default="top",
        description="Reddit sort: hot, top, new, rising",
    )
    limit: int = Field(default=10, ge=1, le=25)


class GetTwitterSignalsParams(BaseModel):
    stacks: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=10, ge=1, le=25)


class GetDevToSignalsParams(BaseModel):
    stacks: list[str] = Field(min_length=1, max_length=10)
    top_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Articles published in the last N days, sorted by reactions",
    )
    limit: int = Field(default=10, ge=1, le=30)


class GetTrendingTopicsParams(BaseModel):
    stacks: list[str] = Field(
        min_length=1,
        max_length=10,
        description="Tech stacks to analyse for trending topics",
    )
    sources: list[SocialSource] = Field(
        default_factory=list,
        description="Sources to aggregate; defaults to all available sources",
    )
    limit: int = Field(default=10, ge=1, le=25)


# ── Tool result models ────────────────────────────────────────────────────────


class SocialSignalsResult(BaseModel):
    signals: list[dict[str, Any]]
    total_count: int
    stacks_queried: list[str]
    source: str
    fetched_at: str


class TrendingTopicsResult(BaseModel):
    topics: list[dict[str, Any]]
    total_signals_analysed: int
    stacks_queried: list[str]
    sources_queried: list[str]
    fetched_at: str
