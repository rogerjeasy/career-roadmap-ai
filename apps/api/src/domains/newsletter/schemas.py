"""Newsletter domain — Pydantic schemas for the user's email digest preferences.

A single preferences document per user (doc id == ``user_id``) controls whether
they receive the career digest, how often, and which topic streams are included.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NewsletterFrequency = Literal["weekly", "biweekly", "monthly"]

_VALID_FREQ = ("weekly", "biweekly", "monthly")

# Topic streams the digest can include — kept in sync with the frontend page.
NEWSLETTER_TOPICS = (
    "market_trends",
    "new_opportunities",
    "skill_spotlights",
    "roadmap_nudges",
    "recommended_reading",
)


class NewsletterPrefsUpdate(BaseModel):
    subscribed: bool = False
    frequency: NewsletterFrequency = "weekly"
    topics: list[str] = Field(default_factory=list)


class NewsletterPrefsOut(BaseModel):
    subscribed: bool
    frequency: NewsletterFrequency
    topics: list[str]
    updated_at: datetime | None = None

    @classmethod
    def defaults(cls) -> "NewsletterPrefsOut":
        return cls(subscribed=False, frequency="weekly", topics=[], updated_at=None)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "NewsletterPrefsOut":
        freq = doc.get("frequency", "weekly")
        return cls(
            subscribed=bool(doc.get("subscribed", False)),
            frequency=freq if freq in _VALID_FREQ else "weekly",
            topics=list(doc.get("topics", [])),
            updated_at=doc.get("updated_at"),
        )


# ── Generated digest ───────────────────────────────────────────────────────────


class DigestArticle(BaseModel):
    title: str
    why: str = ""  # why it matters to this user
    url: str | None = None


class DigestPerson(BaseModel):
    name: str
    reason: str = ""  # why worth following
    handle: str | None = None


class NewsletterDigest(BaseModel):
    """A generated weekly digest: industry summary, reading, people, one action."""

    period_label: str = ""
    summary: str = ""
    articles: list[DigestArticle] = Field(default_factory=list)
    people_to_follow: list[DigestPerson] = Field(default_factory=list)
    action_item: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    has_data: bool = False
    generated_at: datetime | None = None

    @classmethod
    def empty(cls) -> "NewsletterDigest":
        return cls(has_data=False)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "NewsletterDigest":
        articles = [
            DigestArticle.model_validate(a)
            for a in doc.get("articles", [])
            if isinstance(a, dict)
        ]
        people = [
            DigestPerson.model_validate(p)
            for p in doc.get("people_to_follow", [])
            if isinstance(p, dict)
        ]
        return cls(
            period_label=doc.get("period_label", ""),
            summary=doc.get("summary", ""),
            articles=articles,
            people_to_follow=people,
            action_item=doc.get("action_item", ""),
            confidence=float(doc.get("confidence", 0.5) or 0.5),
            has_data=bool(doc.get("summary") or articles),
            generated_at=doc.get("generated_at") or doc.get("created_at"),
        )
