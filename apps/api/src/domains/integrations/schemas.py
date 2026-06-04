"""Integrations domain — request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.domains.integrations.providers import IntegrationProvider


class IntegrationStatusOut(BaseModel):
    provider: IntegrationProvider
    name: str
    description: str
    consent_note: str
    # True when the server has OAuth client credentials configured for this provider.
    available: bool
    # True when the current user has an active connection.
    connected: bool
    # Human-readable account label (e.g. GitHub login / email), when known.
    account_label: str | None = None
    connected_at: datetime | None = None
    scopes: list[str] = []


class AuthorizeOut(BaseModel):
    authorization_url: str
