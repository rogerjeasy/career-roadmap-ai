"""Notifications domain — Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NotificationTone = Literal["info", "success", "warn"]


class NotificationCreate(BaseModel):
    """Payload for creating a notification (used internally by other services)."""

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=1000)
    tone: NotificationTone = "info"
    link: str | None = Field(default=None, max_length=500)


class NotificationOut(BaseModel):
    """Notification as returned to clients."""

    id: str
    title: str
    body: str
    tone: NotificationTone
    link: str | None
    read: bool
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "NotificationOut":
        tone = doc.get("tone", "info")
        return cls(
            id=doc["id"],
            title=doc.get("title", ""),
            body=doc.get("body", ""),
            tone=tone if tone in ("info", "success", "warn") else "info",
            link=doc.get("link"),
            read=bool(doc.get("read", False)),
            created_at=doc["created_at"],
        )


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int
