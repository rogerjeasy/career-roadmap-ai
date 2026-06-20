"""Plan Version Snapshots domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SnapshotCreate(BaseModel):
    roadmap_id: str = Field(min_length=1)
    label: str = Field(default="", max_length=160)


class SnapshotOut(BaseModel):
    id: str
    roadmap_id: str
    label: str
    summary: str
    phase_count: int
    auto: bool
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "SnapshotOut":
        return cls(
            id=doc.get("id", ""),
            roadmap_id=doc.get("roadmap_id", ""),
            label=doc.get("label", ""),
            summary=doc.get("summary", ""),
            phase_count=int(doc.get("phase_count", 0) or 0),
            auto=bool(doc.get("auto", False)),
            created_at=doc.get("created_at"),
        )
