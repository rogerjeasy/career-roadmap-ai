"""Career Twin domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TwinVoice = Literal["supportive", "direct", "playful", "stoic", "analytical"]
CheckinStatus = Literal["open", "answered"]

_VALID_VOICE = ("supportive", "direct", "playful", "stoic", "analytical")


class TwinPersonaUpsert(BaseModel):
    name: str = Field(default="Your Career Twin", min_length=1, max_length=80)
    voice: TwinVoice = "supportive"
    focus: str = Field(default="", max_length=400)
    check_in_enabled: bool = True


class TwinPersonaOut(BaseModel):
    name: str
    voice: TwinVoice
    focus: str
    check_in_enabled: bool
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> "TwinPersonaOut":
        doc = doc or {}
        voice = doc.get("voice", "supportive")
        return cls(
            name=doc.get("name", "Your Career Twin"),
            voice=voice if voice in _VALID_VOICE else "supportive",
            focus=doc.get("focus", ""),
            check_in_enabled=bool(doc.get("check_in_enabled", True)),
            created_at=doc.get("created_at"),
        )


class CheckinReply(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)
    mood: int | None = Field(default=None, ge=1, le=5)


class DailyCheckinOut(BaseModel):
    id: str
    date: str
    greeting: str
    prompt: str
    focus_suggestion: str
    user_reply: str
    twin_response: str
    mood: int | None = None
    status: CheckinStatus
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "DailyCheckinOut":
        status = doc.get("status", "open")
        return cls(
            id=doc.get("id", ""),
            date=doc.get("date", ""),
            greeting=doc.get("greeting", ""),
            prompt=doc.get("prompt", ""),
            focus_suggestion=doc.get("focus_suggestion", ""),
            user_reply=doc.get("user_reply", ""),
            twin_response=doc.get("twin_response", ""),
            mood=doc.get("mood"),
            status=status if status in ("open", "answered") else "open",
            created_at=doc.get("created_at"),
        )
