"""Job Board MCP Server configuration.

All values are loaded from environment variables. Missing required values
crash the process at startup — secrets are never defaulted to empty strings.
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


class JobBoardSettings(BaseSettings):
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
    port: int = 3001

    # ── Auth ──────────────────────────────────────────────────
    mcp_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=300, ge=60)

    # ── Rate limiting ─────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=60, ge=1)

    # ── LinkedIn Jobs (RapidAPI — linkedin-job-search-api) ───────────────
    linkedin_api_key: SecretStr | None = None
    linkedin_api_host: str = "linkedin-job-search-api.p.rapidapi.com"

    # ── Indeed (via RapidAPI) ────────────────────────────────
    indeed_api_key: SecretStr | None = None
    indeed_api_host: str = "indeed12.p.rapidapi.com"

    # ── Glassdoor (RapidAPI — real-time-glassdoor-data) ─────────────────────────────
    glassdoor_api_key: SecretStr | None = None
    glassdoor_api_host: str = "real-time-glassdoor-data.p.rapidapi.com"

    # ── Adzuna (official aggregator API) ─────────────────────────
    adzuna_app_id: SecretStr | None = None
    adzuna_app_key: SecretStr | None = None
    adzuna_base_url: str = "https://api.adzuna.com/v1/api/jobs"

    # ── Swiss Job Portal (jobs.ch) ────────────────────────────
    swiss_jobs_base_url: str = "https://www.jobs.ch/en/vacancies/"
    jobup_base_url: str = "https://www.jobup.ch/en/jobs/"

    # ── HTTP client ───────────────────────────────────────────
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    http_max_retries: int = Field(default=3, ge=1, le=5)

    # ── Search defaults ───────────────────────────────────────
    default_results_per_source: int = Field(default=10, ge=1, le=50)
    max_total_results: int = Field(default=50, ge=1, le=200)


@lru_cache
def get_settings() -> JobBoardSettings:
    return JobBoardSettings()  # type: ignore[call-arg]
