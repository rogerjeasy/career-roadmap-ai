"""Networking domain — contacts, events, and outreach log."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ContactStatus = Literal["to_reach", "contacted", "responded", "connected"]
EventKind = Literal["meetup", "conference", "webinar", "ama"]
OutreachChannel = Literal["email", "linkedin", "in_person", "other"]


def _coerce(value: str, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


# ── Contacts ──────────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    status: ContactStatus = "to_reach"
    reason: str | None = Field(default=None, max_length=500)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    status: ContactStatus | None = None
    reason: str | None = Field(default=None, max_length=500)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ContactOut(BaseModel):
    id: str
    name: str
    role: str
    company: str
    status: ContactStatus
    reason: str | None
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ContactOut":
        return cls(
            id=doc["id"],
            name=doc.get("name", ""),
            role=doc.get("role", ""),
            company=doc.get("company", ""),
            status=_coerce(
                doc.get("status", "to_reach"),
                ("to_reach", "contacted", "responded", "connected"),
                "to_reach",
            ),  # type: ignore[arg-type]
            reason=doc.get("reason"),
            created_at=doc["created_at"],
        )


# ── Events ────────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: EventKind = "meetup"
    date_label: str = Field(default="", max_length=80)
    location: str = Field(default="", max_length=200)
    is_online: bool = False


class EventOut(BaseModel):
    id: str
    title: str
    kind: EventKind
    date_label: str
    location: str
    is_online: bool
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "EventOut":
        return cls(
            id=doc["id"],
            title=doc.get("title", ""),
            kind=_coerce(
                doc.get("kind", "meetup"),
                ("meetup", "conference", "webinar", "ama"),
                "meetup",
            ),  # type: ignore[arg-type]
            date_label=doc.get("date_label", ""),
            location=doc.get("location", ""),
            is_online=bool(doc.get("is_online", False)),
            created_at=doc["created_at"],
        )


# ── Outreach log ──────────────────────────────────────────────────────────────

class OutreachCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=200)
    channel: OutreachChannel = "email"
    note: str = Field(default="", max_length=1000)


class OutreachOut(BaseModel):
    id: str
    contact_name: str
    channel: OutreachChannel
    note: str
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "OutreachOut":
        return cls(
            id=doc["id"],
            contact_name=doc.get("contact_name", ""),
            channel=_coerce(
                doc.get("channel", "email"),
                ("email", "linkedin", "in_person", "other"),
                "email",
            ),  # type: ignore[arg-type]
            note=doc.get("note", ""),
            created_at=doc["created_at"],
        )
