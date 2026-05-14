"""Course Catalogue MCP Server configuration.

All values are loaded from environment variables. Sources without credentials
are silently skipped at startup — only edX requires no API key.
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


class CourseCatalogueSettings(BaseSettings):
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
    port: int = 3002

    # ── Auth ──────────────────────────────────────────────────
    mcp_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=3600, ge=60)  # courses stable; 1h default

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=30, ge=1)

    # ── Coursera (via RapidAPI) ───────────────────────────────
    coursera_api_key: SecretStr | None = None
    coursera_api_host: str = "coursera.p.rapidapi.com"

    # ── Udemy (via RapidAPI) ─────────────────────────────────
    udemy_api_key: SecretStr | None = None
    udemy_api_host: str = "udemy-paid-and-free-courses.p.rapidapi.com"

    # ── YouTube Data API v3 ───────────────────────────────────
    youtube_api_key: SecretStr | None = None
    youtube_base_url: str = "https://www.googleapis.com/youtube/v3"

    # ── O'Reilly Learning (via RapidAPI) ─────────────────────
    oreilly_api_key: SecretStr | None = None
    oreilly_api_host: str = "oreilly-learning.p.rapidapi.com"

    # ── edX public discovery (no key required) ────────────────
    edx_discovery_url: str = "https://discovery.edx.org"

    # ── HTTP client ───────────────────────────────────────────
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    # ── Search defaults ───────────────────────────────────────
    default_results_per_source: int = Field(default=10, ge=1, le=50)
    max_total_results: int = Field(default=50, ge=1, le=200)


@lru_cache
def get_settings() -> CourseCatalogueSettings:
    return CourseCatalogueSettings()  # type: ignore[call-arg]
