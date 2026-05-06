"""Agent framework configuration — loaded from environment variables.

Deliberately independent of apps/api/src/config.py. Both packages read
the same .env file but each validates only the slice it owns. This keeps
the agents package free of any FastAPI / SQLAlchemy / Firebase imports.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime environment ───────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── LLM ──────────────────────────────────────────────────
    anthropic_api_key: SecretStr
    orchestrator_model: str = "claude-sonnet-4-6"
    clarification_model: str = "claude-sonnet-4-6"
    validator_model: str = "claude-haiku-4-5-20251001"
    market_intelligence_model: str = "claude-haiku-4-5-20251001"
    roadmap_generation_model: str = "claude-sonnet-4-6"
    roadmap_milestone_model: str = "claude-haiku-4-5-20251001"

    # ── Celery / Redis ────────────────────────────────────────
    celery_broker_url: RedisDsn
    celery_result_backend: RedisDsn
    redis_url: RedisDsn

    # ── Orchestrator tuning ───────────────────────────────────
    completeness_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_clarification_rounds: int = Field(default=3, ge=1)
    max_clarification_questions: int = Field(default=3, ge=1, le=5)
    agent_task_timeout_seconds: int = Field(default=120, ge=10)
    orchestrator_max_iterations: int = Field(default=15, ge=5)

    # ── MCP server endpoints (all optional) ──────────────────
    # When set, HttpMCPClient is used; otherwise StubMCPClient is used automatically.
    mcp_job_board_url: str | None = None
    mcp_salary_benchmark_url: str | None = None
    mcp_github_trends_url: str | None = None
    mcp_social_signals_url: str | None = None
    mcp_course_catalog_url: str | None = None
    mcp_linkedin_profile_url: str | None = None
    mcp_industry_news_url: str | None = None
    mcp_timeout_seconds: float = Field(default=30.0, gt=0)

    # ── Learning Resources tuning ─────────────────────────────
    learning_resources_max_gaps: int = Field(default=10, ge=1, le=50)

    # ── Networking & Outreach tuning ──────────────────────────
    networking_model: str = "claude-haiku-4-5-20251001"
    networking_max_outreach_drafts: int = Field(default=3, ge=1, le=10)
    networking_max_events: int = Field(default=10, ge=1, le=50)

    # ── Event streaming ───────────────────────────────────────
    event_channel_ttl_seconds: int = Field(default=3600)


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()  # type: ignore[call-arg]


agent_settings = get_agent_settings()
