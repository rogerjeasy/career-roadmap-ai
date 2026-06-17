"""Evidence Vault domain — Pydantic schemas.

Stores concrete proof of a user's professional progress: achievements,
certifications, shipped projects, recommendations and metrics. Each item can be
linked back to the skills it evidences, so the roadmap and CV gap analysis can
reference real, user-owned proof rather than self-reported claims.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EvidenceType = Literal[
    "achievement",
    "certification",
    "project",
    "recommendation",
    "metric",
    "other",
]

_VALID_TYPES = (
    "achievement",
    "certification",
    "project",
    "recommendation",
    "metric",
    "other",
)


class EvidenceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    type: EvidenceType = "achievement"
    link: str = Field(default="", max_length=1000)
    date_label: str = Field(default="", max_length=60)
    skills: list[str] = Field(default_factory=list)


class EvidenceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    type: EvidenceType | None = None
    link: str | None = Field(default=None, max_length=1000)
    date_label: str | None = Field(default=None, max_length=60)
    skills: list[str] | None = None

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class EvidenceOut(BaseModel):
    id: str
    title: str
    description: str
    type: EvidenceType
    link: str
    date_label: str
    skills: list[str]
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "EvidenceOut":
        ev_type = doc.get("type", "achievement")
        return cls(
            id=doc["id"],
            title=doc.get("title", ""),
            description=doc.get("description", ""),
            type=ev_type if ev_type in _VALID_TYPES else "other",
            link=doc.get("link", ""),
            date_label=doc.get("date_label", ""),
            skills=list(doc.get("skills", [])),
            created_at=doc["created_at"],
        )
