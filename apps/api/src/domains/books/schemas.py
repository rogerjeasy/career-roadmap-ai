"""Books domain — Pydantic schemas for the user's reading list."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

BookStatus = Literal["reading", "queued", "done"]


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(default="", max_length=200)
    why: str = Field(default="", max_length=2000)
    status: BookStatus = "queued"
    tag: str = Field(default="", max_length=60)
    phase: str = Field(default="", max_length=200)
    takeaways: list[str] = Field(default_factory=list)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    why: str | None = Field(default=None, max_length=2000)
    status: BookStatus | None = None
    tag: str | None = Field(default=None, max_length=60)
    phase: str | None = Field(default=None, max_length=200)
    takeaways: list[str] | None = None

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class BookOut(BaseModel):
    id: str
    title: str
    author: str
    why: str
    status: BookStatus
    tag: str
    phase: str
    takeaways: list[str]
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "BookOut":
        status = doc.get("status", "queued")
        return cls(
            id=doc["id"],
            title=doc.get("title", ""),
            author=doc.get("author", ""),
            why=doc.get("why", ""),
            status=status if status in ("reading", "queued", "done") else "queued",
            tag=doc.get("tag", ""),
            phase=doc.get("phase", ""),
            takeaways=list(doc.get("takeaways", [])),
            created_at=doc["created_at"],
        )
