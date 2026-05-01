"""Application configuration loaded from environment variables.

All env vars are validated at startup. Missing or malformed values
raise immediately rather than failing later in production.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────
    app_name: str = "Career Roadmap AI"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ── Server ────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── CORS ──────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"]
    )

    # ── Database ──────────────────────────────────────────
    database_url: PostgresDsn | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── Redis ─────────────────────────────────────────────
    redis_url: RedisDsn
    redis_session_ttl_seconds: int = 60 * 60 * 24  # 24 h

    # ── Celery ────────────────────────────────────────────
    celery_broker_url: RedisDsn
    celery_result_backend: RedisDsn

    # ── Firebase Auth ─────────────────────────────────────
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None   # path to service account JSON (dev)
    firebase_credentials_json: str | None = None   # JSON string (CI / cloud env var)
    # Web API Key — Firebase Console → Project Settings → General → Web API Key
    # Required for server-side email/password sign-in and token refresh via REST API
    firebase_web_api_key: str | None = None

    # ── Rate limiting ─────────────────────────────────────
    rate_limit_per_minute: int = 60

    # ── LLM providers ─────────────────────────────────────
    anthropic_api_key: SecretStr
    openai_api_key: SecretStr | None = None
    default_llm_model: str = "claude-3-5-sonnet-20241022"

    # ── Observability ─────────────────────────────────────
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 1.0
    sentry_send_default_pii: bool = False  # toggle ON only after privacy review
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "career-roadmap-api"
    prometheus_metrics_enabled: bool = True

    # ── Storage ───────────────────────────────────────────
    blob_storage_provider: Literal["local", "azure", "s3"] = "local"
    blob_storage_path: str = "./storage"
    max_upload_size_mb: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings — loaded once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()