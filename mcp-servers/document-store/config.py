"""Document Store MCP Server configuration."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apps", "api", ".env",
)


class DocumentStoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 3009

    mcp_api_key: str = ""

    redis_url: str = Field(default="redis://localhost:6379/8", validation_alias="mcp_redis_url")
    cache_ttl_seconds: int = Field(default=300, ge=60)

    rate_limit_per_minute: int = Field(default=30, ge=1)

    # Storage provider: "local" | "azure" | "cloudinary"
    storage_provider: Literal["local", "azure", "cloudinary"] = Field(
        default="local", validation_alias="blob_storage_provider"
    )

    # Local storage
    local_storage_path: str = Field(
        default="data/documents",
        description="Base directory for local file storage (relative to project root or absolute)",
    )

    # Azure Blob Storage
    azure_storage_connection_string: SecretStr | None = None
    azure_storage_container: str = "career-roadmap-documents"

    # Cloudinary (matches names used by the RAG layer and AgentSettings)
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_upload_folder: str = "career-roadmap/documents"

    # Document limits
    max_file_size_mb: int = Field(default=10, ge=1, le=50)
    max_documents_per_user: int = Field(default=20, ge=1)

    # Sentry (optional)
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> DocumentStoreSettings:
    return DocumentStoreSettings()  # type: ignore[call-arg]
