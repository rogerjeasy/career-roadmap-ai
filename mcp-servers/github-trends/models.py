"""Pydantic data models for the GitHub Trends MCP server."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TrendingRepo(BaseModel):
    """A trending GitHub repository."""

    id: int
    name: str
    full_name: str
    description: str | None = None
    url: str
    stars: int
    forks: int
    open_issues: int
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    created_at: str | None = None
    pushed_at: str | None = None
    stars_today: int | None = None  # estimated — not official GitHub metric

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "url": self.url,
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "language": self.language,
            "topics": self.topics,
            "created_at": self.created_at,
            "pushed_at": self.pushed_at,
        }


class GoodFirstIssue(BaseModel):
    """A GitHub issue labelled good-first-issue."""

    id: int
    number: int
    title: str
    url: str
    repo_full_name: str
    repo_url: str
    language: str | None = None
    labels: list[str] = Field(default_factory=list)
    comments: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "repo_full_name": self.repo_full_name,
            "repo_url": self.repo_url,
            "language": self.language,
            "labels": self.labels,
            "comments": self.comments,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── Tool input / output schemas ────────────────────────────────────────────────


class GetTrendingReposParams(BaseModel):
    language: str = Field(default="python", min_length=1, max_length=50)
    since_days: int = Field(default=7, ge=1, le=30)
    limit: int = Field(default=15, ge=1, le=30)
    topic: str | None = Field(default=None, max_length=50)
    min_stars: int = Field(default=50, ge=0)


class GetTrendingReposResult(BaseModel):
    repos: list[dict[str, Any]]
    total_count: int
    language: str
    since_days: int
    fetched_at: str


class GetGoodFirstIssuesParams(BaseModel):
    language: str = Field(default="python", min_length=1, max_length=50)
    limit: int = Field(default=15, ge=1, le=30)
    topic: str | None = Field(default=None, max_length=50)
    max_comments: int = Field(default=5, ge=0)


class GetGoodFirstIssuesResult(BaseModel):
    issues: list[dict[str, Any]]
    total_count: int
    language: str
    fetched_at: str
