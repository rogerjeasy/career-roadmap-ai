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
