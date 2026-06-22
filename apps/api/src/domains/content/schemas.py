"""Content Engine domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ContentKind = Literal["linkedin_post", "build_in_public", "milestone_announcement"]
ContentTone = Literal["professional", "conversational", "bold", "reflective"]
ContentSource = Literal["roadmap_milestone", "freeform"]
ContentStatus = Literal["draft", "approved", "published"]

_KINDS = ("linkedin_post", "build_in_public", "milestone_announcement")
_TONES = ("professional", "conversational", "bold", "reflective")
_STATUSES = ("draft", "approved", "published")


class ContentGenerateInput(BaseModel):
    kind: ContentKind = "linkedin_post"
    tone: ContentTone = "professional"
    source: ContentSource = "roadmap_milestone"
    # Optional specific milestone/achievement to anchor the post on.
    milestone: str = Field(default="", max_length=600)
    extra_context: str = Field(default="", max_length=2000)


class ContentStatusUpdate(BaseModel):
    status: ContentStatus


class ContentDraftOut(BaseModel):
    id: str
    kind: ContentKind
    tone: ContentTone
    title: str
    content: str
    hashtags: list[str] = Field(default_factory=list)
    status: ContentStatus
    based_on: str = ""
    created_at: datetime | None = None
    published_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ContentDraftOut":
        kind = doc.get("kind", "linkedin_post")
        tone = doc.get("tone", "professional")
        status = doc.get("status", "draft")
        return cls(
            id=doc.get("id", ""),
            kind=kind if kind in _KINDS else "linkedin_post",
            tone=tone if tone in _TONES else "professional",
            title=doc.get("title", ""),
            content=doc.get("content", ""),
            hashtags=list(doc.get("hashtags", []) or []),
            status=status if status in _STATUSES else "draft",
            based_on=doc.get("based_on", ""),
            created_at=doc.get("created_at"),
            published_at=doc.get("published_at"),
        )
