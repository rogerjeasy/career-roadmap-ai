"""Open-Source Contribution Finder domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OssIssue(BaseModel):
    issue_id: int
    title: str
    url: str
    repo: str
    repo_url: str
    language: str = ""
    labels: list[str] = Field(default_factory=list)
    comments: int = 0
    updated_at: str = ""
    match_score: int = 0
    match_reason: str = ""


class OssSearchResult(BaseModel):
    issues: list[OssIssue]
    languages_used: list[str]
    query_used: str
    note: str = ""


class OssBookmarkCreate(BaseModel):
    issue_id: int
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=1000)
    repo: str = Field(default="", max_length=300)
    language: str = Field(default="", max_length=60)
    labels: list[str] = Field(default_factory=list, max_length=30)
    status: str = Field(default="saved", max_length=30)


class OssBookmarkOut(BaseModel):
    id: str
    issue_id: int
    title: str
    url: str
    repo: str
    language: str
    labels: list[str]
    status: str
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "OssBookmarkOut":
        return cls(
            id=doc.get("id", ""),
            issue_id=int(doc.get("issue_id", 0) or 0),
            title=doc.get("title", ""),
            url=doc.get("url", ""),
            repo=doc.get("repo", ""),
            language=doc.get("language", ""),
            labels=list(doc.get("labels", []) or []),
            status=doc.get("status", "saved"),
            created_at=doc.get("created_at"),
        )
