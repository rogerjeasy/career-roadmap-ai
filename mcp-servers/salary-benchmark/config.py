"""Salary Benchmark MCP Server configuration."""
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


class SalaryBenchmarkSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 3003

    mcp_api_key: str = ""

    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=3600, ge=60)  # salary data changes slowly

    rate_limit_per_minute: int = Field(default=30, ge=1)

    # Glassdoor via RapidAPI — also used by the job-board for salary enrichment
    glassdoor_api_key: SecretStr | None = None
    glassdoor_api_host: str = "real-time-glassdoor-data.p.rapidapi.com"

    # levels.fyi unofficial API (no key required but respects rate limits)
    levels_fyi_base_url: str = "https://www.levels.fyi"
    levels_fyi_enabled: bool = True

    http_timeout_seconds: float = Field(default=20.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    default_currency: str = "CHF"


@lru_cache
def get_settings() -> SalaryBenchmarkSettings:
    return SalaryBenchmarkSettings()  # type: ignore[call-arg]
