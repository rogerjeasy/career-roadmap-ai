"""Career Storytelling Studio domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StoryFormat = Literal[
    "resume_bullets", "linkedin_about", "cover_letter", "interview_story"
]
StoryTone = Literal["professional", "confident", "warm", "concise"]

_VALID_FORMATS = ("resume_bullets", "linkedin_about", "cover_letter", "interview_story")


class StoryGenerateInput(BaseModel):
    format: StoryFormat = "resume_bullets"
    tone: StoryTone = "professional"
    target_role: str = Field(default="", max_length=160)
    target_company: str = Field(default="", max_length=160)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    extra_context: str = Field(default="", max_length=2000)


class StoryDraftOut(BaseModel):
    id: str
    format: StoryFormat
    tone: StoryTone
    target_role: str
    target_company: str
    title: str
    content: str
    highlights: list[str]
    tips: list[str]
    evidence_titles: list[str]
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "StoryDraftOut":
        fmt = doc.get("format", "resume_bullets")
        tone = doc.get("tone", "professional")
        return cls(
            id=doc.get("id", ""),
            format=fmt if fmt in _VALID_FORMATS else "resume_bullets",
            tone=tone if tone in ("professional", "confident", "warm", "concise") else "professional",
            target_role=doc.get("target_role", ""),
            target_company=doc.get("target_company", ""),
            title=doc.get("title", ""),
            content=doc.get("content", ""),
            highlights=list(doc.get("highlights", []) or []),
            tips=list(doc.get("tips", []) or []),
            evidence_titles=list(doc.get("evidence_titles", []) or []),
            created_at=doc.get("created_at"),
        )
