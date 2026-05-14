"""GitHub Trends MCP Server configuration."""
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


class GitHubTrendsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 3004

    mcp_api_key: str = ""

    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=1800, ge=60)  # trending data: 30-min TTL

    rate_limit_per_minute: int = Field(default=30, ge=1)

    # GitHub Personal Access Token (optional but raises rate limit from 60→5000 req/hr)
    github_token: SecretStr | None = None
    github_api_base_url: str = "https://api.github.com"

    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    default_language: str = "python"
    trending_since_days: int = Field(default=7, ge=1, le=30)
    default_limit: int = Field(default=15, ge=1, le=30)


@lru_cache
def get_settings() -> GitHubTrendsSettings:
    return GitHubTrendsSettings()  # type: ignore[call-arg]
