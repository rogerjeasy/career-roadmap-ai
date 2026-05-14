"""Calendar MCP Server configuration.

All values are loaded from environment variables. Both Google Calendar and
Outlook (Microsoft Graph) providers are always registered — they authenticate
via per-request OAuth access tokens passed by the calling agent.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Centralised .env — one source of truth for the whole monorepo
_API_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apps", "api", ".env",
)


class CalendarSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime ───────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 3006

    # ── Auth ──────────────────────────────────────────────────
    mcp_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    # list_upcoming responses are cached for 5 minutes; write ops are not cached
    cache_ttl_seconds: int = Field(default=300, ge=60)

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=30, ge=1)

    # ── HTTP client ───────────────────────────────────────────
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    # ── OAuth credentials (server-side token store) ───────────
    google_oauth_client_id: SecretStr | None = None
    google_oauth_client_secret: SecretStr | None = None
    microsoft_oauth_client_id: SecretStr | None = None
    microsoft_oauth_client_secret: SecretStr | None = None
    calendar_token_encryption_key: SecretStr | None = None

    # ── Calendar defaults ─────────────────────────────────────
    default_reminder_minutes: list[int] = Field(default_factory=lambda: [60, 10])
    max_events_per_week: int = Field(default=50, ge=1, le=200)
    max_list_results: int = Field(default=50, ge=1, le=250)
    default_timezone: str = "UTC"


@lru_cache
def get_settings() -> CalendarSettings:
    return CalendarSettings()  # type: ignore[call-arg]
