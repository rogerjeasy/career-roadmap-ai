"""Web Push domain — Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: PushKeys
    expiration_time: float | None = None


class PushUnsubscribe(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)


class PushConfig(BaseModel):
    enabled: bool
    public_key: str | None = None


class PushSendResult(BaseModel):
    sent: int
    failed: int
    enabled: bool
    detail: str = ""
