"""Feedback domain — Pydantic schemas for user help requests and feedback."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

FeedbackCategory = Literal["bug", "idea", "question", "praise", "other"]

_VALID_CATEGORIES = ("bug", "idea", "question", "praise", "other")


class FeedbackCreate(BaseModel):
    category: FeedbackCategory = "idea"
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    # Optional 1–5 satisfaction rating; omitted for pure bug reports / questions.
    rating: int | None = Field(default=None, ge=1, le=5)


class FeedbackOut(BaseModel):
    id: str
    category: FeedbackCategory
    subject: str
    message: str
    rating: int | None
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "FeedbackOut":
        category = doc.get("category", "other")
        return cls(
            id=doc["id"],
            category=category if category in _VALID_CATEGORIES else "other",
            subject=doc.get("subject", ""),
            message=doc.get("message", ""),
            rating=doc.get("rating"),
            created_at=doc["created_at"],
        )
