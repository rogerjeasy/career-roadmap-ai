"""AI Outreach Drafting domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

OutreachChannel = Literal["email", "linkedin", "other"]
OutreachTone = Literal["warm", "professional", "concise", "enthusiastic"]
DraftStatus = Literal["draft", "approved", "sent"]

_CHANNELS = ("email", "linkedin", "other")
_STATUS = ("draft", "approved", "sent")


class OutreachDraftRequest(BaseModel):
    recipient_name: str = Field(default="", max_length=160)
    recipient_role: str = Field(default="", max_length=200)
    channel: OutreachChannel = "email"
    tone: OutreachTone = "warm"
    goal: str = Field(min_length=1, max_length=600)
    context: str = Field(default="", max_length=2000)


class OutreachEdit(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=6000)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class OutreachDraftOut(BaseModel):
    id: str
    recipient_name: str
    recipient_role: str
    channel: OutreachChannel
    tone: OutreachTone
    goal: str
    subject: str
    body: str
    status: DraftStatus
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "OutreachDraftOut":
        channel = doc.get("channel", "email")
        tone = doc.get("tone", "warm")
        status = doc.get("status", "draft")
        return cls(
            id=doc.get("id", ""),
            recipient_name=doc.get("recipient_name", ""),
            recipient_role=doc.get("recipient_role", ""),
            channel=channel if channel in _CHANNELS else "email",
            tone=tone if tone in ("warm", "professional", "concise", "enthusiastic") else "warm",
            goal=doc.get("goal", ""),
            subject=doc.get("subject", ""),
            body=doc.get("body", ""),
            status=status if status in _STATUS else "draft",
            created_at=doc.get("created_at"),
        )
