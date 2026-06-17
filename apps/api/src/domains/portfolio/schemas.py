"""Portfolio domain — Pydantic schemas.

A showcase of the user's shipped work: projects, case studies and demos. Each
entry records the tech/skills used and a few highlights, so it doubles as
structured evidence the CV and opportunity-matching flows can draw on.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["live", "in_progress", "archived"]

_VALID_STATUS = ("live", "in_progress", "archived")


class PortfolioItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    role: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=1000)
    repo_url: str = Field(default="", max_length=1000)
    status: ProjectStatus = "live"
    date_label: str = Field(default="", max_length=60)
    tech: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class PortfolioItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    role: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    repo_url: str | None = Field(default=None, max_length=1000)
    status: ProjectStatus | None = None
    date_label: str | None = Field(default=None, max_length=60)
    tech: list[str] | None = None
    highlights: list[str] | None = None

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class PortfolioItemOut(BaseModel):
    id: str
    title: str
    description: str
    role: str
    url: str
    repo_url: str
    status: ProjectStatus
    date_label: str
    tech: list[str]
    highlights: list[str]
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "PortfolioItemOut":
        item_status = doc.get("status", "live")
        return cls(
            id=doc["id"],
            title=doc.get("title", ""),
            description=doc.get("description", ""),
            role=doc.get("role", ""),
            url=doc.get("url", ""),
            repo_url=doc.get("repo_url", ""),
            status=item_status if item_status in _VALID_STATUS else "live",
            date_label=doc.get("date_label", ""),
            tech=list(doc.get("tech", [])),
            highlights=list(doc.get("highlights", [])),
            created_at=doc["created_at"],
        )
