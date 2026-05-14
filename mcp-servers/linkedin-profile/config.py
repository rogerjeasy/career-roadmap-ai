"""LinkedIn Profile MCP Server configuration."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apps", "api", ".env",
)


class LinkedInProfileSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 3008

    mcp_api_key: str = ""

    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=3600, ge=60)  # profile data changes slowly

    rate_limit_per_minute: int = Field(default=20, ge=1)

    # LinkedIn Profile API via RapidAPI
    linkedin_api_key: SecretStr | None = None
    linkedin_api_host: str = "linkedin-data-api.p.rapidapi.com"

    http_timeout_seconds: float = Field(default=20.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    # Sentry (optional)
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> LinkedInProfileSettings:
    return LinkedInProfileSettings()  # type: ignore[call-arg]
