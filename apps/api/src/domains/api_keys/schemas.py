"""Public API Keys domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    last4: str
    revoked: bool
    last_used_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ApiKeyOut":
        return cls(
            id=doc.get("id", ""),
            name=doc.get("name", ""),
            prefix=doc.get("prefix", ""),
            last4=doc.get("last4", ""),
            revoked=bool(doc.get("revoked", False)),
            last_used_at=doc.get("last_used_at"),
            created_at=doc.get("created_at"),
        )


class ApiKeyCreated(ApiKeyOut):
    """Returned only at creation time — carries the full secret once."""

    key: str


class PublicProfile(BaseModel):
    """Read model returned by the public API for the key's owner."""

    user_id: str
    target_role: str | None = None
    current_role: str | None = None
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    has_roadmap: bool = False
    roadmap_summary: str | None = None


class PublicPhase(BaseModel):
    order: int
    title: str
    duration_weeks: int = 0
    milestones: list[str] = Field(default_factory=list)


class PublicRoadmap(BaseModel):
    has_roadmap: bool
    summary: str | None = None
    phase_count: int = 0
    phases: list[PublicPhase] = Field(default_factory=list)
