"""Mentorship domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SessionStatus = Literal["requested", "accepted", "declined", "completed"]


# ── Mentor profiles ───────────────────────────────────────────────────────────


class MentorProfileUpsert(BaseModel):
    headline: str = Field(min_length=1, max_length=160)
    bio: str = Field(default="", max_length=2000)
    expertise: list[str] = Field(default_factory=list, max_length=30)
    capacity: int = Field(default=3, ge=1, le=20)
    is_active: bool = True


class MentorProfileOut(BaseModel):
    user_id: str
    name: str
    headline: str
    bio: str
    expertise: list[str]
    capacity: int
    is_active: bool
    # Only populated in the discover feed.
    match_score: int = 0
    match_reason: str = ""
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MentorProfileOut":
        return cls(
            user_id=doc.get("user_id", doc.get("id", "")),
            name=doc.get("name", "A mentor"),
            headline=doc.get("headline", ""),
            bio=doc.get("bio", ""),
            expertise=list(doc.get("expertise", []) or []),
            capacity=int(doc.get("capacity", 3) or 3),
            is_active=bool(doc.get("is_active", True)),
            created_at=doc.get("created_at"),
        )


# ── Sessions ──────────────────────────────────────────────────────────────────


class SessionRequest(BaseModel):
    mentor_id: str = Field(min_length=1)
    topic: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=2000)


class SessionRespond(BaseModel):
    decision: Literal["accepted", "declined"]
    reply: str = Field(default="", max_length=2000)


class MentorSessionOut(BaseModel):
    id: str
    mentor_id: str
    mentor_name: str
    mentee_id: str
    mentee_name: str
    topic: str
    message: str
    reply: str
    status: SessionStatus
    role: Literal["mentor", "mentee"] = "mentee"  # viewer's role in this session
    created_at: datetime | None = None
    responded_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any], viewer_id: str) -> "MentorSessionOut":
        status = doc.get("status", "requested")
        return cls(
            id=doc.get("id", ""),
            mentor_id=doc.get("mentor_id", ""),
            mentor_name=doc.get("mentor_name", "A mentor"),
            mentee_id=doc.get("mentee_id", ""),
            mentee_name=doc.get("mentee_name", "A mentee"),
            topic=doc.get("topic", ""),
            message=doc.get("message", ""),
            reply=doc.get("reply", ""),
            status=status if status in ("requested", "accepted", "declined", "completed") else "requested",
            role="mentor" if viewer_id == doc.get("mentor_id") else "mentee",
            created_at=doc.get("created_at"),
            responded_at=doc.get("responded_at"),
        )


# ── Insider conversations (case studies) ──────────────────────────────────────


class CaseStudyCreate(BaseModel):
    from_role: str = Field(min_length=1, max_length=160)
    to_role: str = Field(min_length=1, max_length=160)
    timeframe_months: int = Field(default=0, ge=0, le=600)
    summary: str = Field(min_length=1, max_length=2000)
    steps: list[str] = Field(default_factory=list, max_length=20)
    lessons: list[str] = Field(default_factory=list, max_length=20)
    is_anonymous: bool = False


class CaseStudyOut(BaseModel):
    id: str
    author_name: str
    from_role: str
    to_role: str
    timeframe_months: int
    summary: str
    steps: list[str]
    lessons: list[str]
    is_mine: bool = False
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any], viewer_id: str | None = None) -> "CaseStudyOut":
        anon = bool(doc.get("is_anonymous", False))
        return cls(
            id=doc.get("id", ""),
            author_name="Anonymous" if anon else doc.get("author_name", "A member"),
            from_role=doc.get("from_role", ""),
            to_role=doc.get("to_role", ""),
            timeframe_months=int(doc.get("timeframe_months", 0) or 0),
            summary=doc.get("summary", ""),
            steps=list(doc.get("steps", []) or []),
            lessons=list(doc.get("lessons", []) or []),
            is_mine=viewer_id == doc.get("author_id") if viewer_id else False,
            created_at=doc.get("created_at"),
        )
