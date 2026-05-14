"""Social Signals MCP Server configuration.

All values are loaded from environment variables. HackerNews and Dev.to
are always available (no API keys required). Reddit uses the public JSON
API by default; Twitter/X requires a Bearer Token.
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


class SocialSignalsSettings(BaseSettings):
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
    port: int = 3005

    # ── Auth ──────────────────────────────────────────────────
    mcp_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    # Social signals decay quickly — 10-minute default TTL
    cache_ttl_seconds: int = Field(default=600, ge=60)

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=60, ge=1)

    # ── Twitter/X Bearer Token (required for Twitter tool) ────
    twitter_bearer_token: SecretStr | None = None

    # ── Reddit (public JSON API — no key required) ────────────
    # Provide OAuth credentials for higher rate limits
    reddit_client_id: SecretStr | None = None
    reddit_client_secret: SecretStr | None = None
    reddit_user_agent: str = "CareerRoadmapAI/1.0 (by /u/career_roadmap_bot)"

    # ── Dev.to API key (optional — increases rate limit) ──────
    devto_api_key: SecretStr | None = None

    # ── HackerNews (Algolia API — always available, no key) ───
    hn_min_score: int = Field(default=10, ge=0, description="Minimum points filter")
    hn_base_url: str = "https://hn.algolia.com/api/v1/search"

    # ── HTTP client ───────────────────────────────────────────
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    # ── Search defaults ───────────────────────────────────────
    default_results_per_source: int = Field(default=10, ge=1, le=50)
    max_total_results: int = Field(default=50, ge=1, le=200)


@lru_cache
def get_settings() -> SocialSignalsSettings:
    return SocialSignalsSettings()  # type: ignore[call-arg]
