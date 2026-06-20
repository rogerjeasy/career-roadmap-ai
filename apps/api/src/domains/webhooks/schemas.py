"""Webhooks domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

# Events a webhook can subscribe to. "*" subscribes to all.
WEBHOOK_EVENTS = (
    "application.created",
    "application.status_changed",
    "credential.issued",
    "roadmap.updated",
    "interview.completed",
    "*",
)


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["*"], max_length=20)


class WebhookOut(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    secret_prefix: str
    last_status: int | None = None
    last_delivery_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "WebhookOut":
        secret = str(doc.get("secret", ""))
        return cls(
            id=doc.get("id", ""),
            url=doc.get("url", ""),
            events=list(doc.get("events", []) or []),
            active=bool(doc.get("active", True)),
            secret_prefix=secret[:12],
            last_status=doc.get("last_status"),
            last_delivery_at=doc.get("last_delivery_at"),
            created_at=doc.get("created_at"),
        )


class WebhookCreated(WebhookOut):
    """Returned only at creation — carries the full signing secret once."""

    secret: str


class WebhookPingResult(BaseModel):
    delivered: bool
    status: int | None = None
    detail: str = ""
