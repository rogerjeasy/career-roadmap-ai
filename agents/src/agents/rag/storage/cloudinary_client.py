"""Cloudinary client for secure raw-file storage.

Stores source documents (PDFs, JSON, DOCX) that feed the ingestion pipeline.
The client is stateless after construction — the Cloudinary SDK uses a
module-level config singleton, so create only one instance per process.

Upload flow:
  1. Caller provides bytes or a local file path.
  2. Client uploads to Cloudinary in the configured folder with
     ``resource_type="raw"`` (no transformations applied).
  3. Returns a CloudinaryAsset with the public_id and secure URL.

For private access, ``signed_url()`` issues a time-limited signed URL
and ``download()`` streams the bytes for ingestion processing.
"""
from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.core.logging import get_logger
from agents.rag.observability import (
    RAG_STORAGE_UPLOAD_DURATION,
    RAG_STORAGE_UPLOAD_TOTAL,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CloudinaryAsset:
    """Reference to a document stored in Cloudinary."""

    public_id: str
    secure_url: str
    resource_type: str
    format: str
    bytes_size: int
    created_at: str


class CloudinaryClient:
    """Uploads and retrieves raw documents from Cloudinary."""

    def __init__(
        self,
        *,
        cloud_name: str,
        api_key: str,
        api_secret: str,
        upload_folder: str = "career-roadmap",
    ) -> None:
        try:
            import cloudinary  # type: ignore[import-untyped]
            import cloudinary.uploader  # type: ignore[import-untyped]
            import cloudinary.utils  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "cloudinary package is required. "
                "Add it to pyproject.toml: cloudinary>=1.40.0"
            ) from exc

        self._cloudinary = cloudinary
        self._uploader = cloudinary.uploader
        self._utils = cloudinary.utils

        self._cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        self._folder = upload_folder

    async def upload(
        self,
        data: bytes | Path,
        *,
        public_id: str | None = None,
        doc_type: str = "document",
        tags: list[str] | None = None,
    ) -> CloudinaryAsset:
        """Upload raw file bytes or a local path to Cloudinary.

        ``resource_type="raw"`` ensures the file is stored and served
        exactly as provided — no image/video transformations are applied.
        """
        t0 = time.monotonic()
        try:
            options: dict[str, Any] = {
                "folder": self._folder,
                "resource_type": "raw",
                "tags": tags or [],
            }
            if public_id:
                options["public_id"] = public_id

            source: Any = io.BytesIO(data) if isinstance(data, bytes) else str(data)

            result = await asyncio.to_thread(
                self._uploader.upload, source, **options
            )
            RAG_STORAGE_UPLOAD_DURATION.observe(time.monotonic() - t0)
            RAG_STORAGE_UPLOAD_TOTAL.labels(status="success").inc()
            logger.info(
                "rag.storage.uploaded",
                public_id=result["public_id"],
                bytes_size=result.get("bytes", 0),
                doc_type=doc_type,
            )
            return CloudinaryAsset(
                public_id=result["public_id"],
                secure_url=result["secure_url"],
                resource_type=result["resource_type"],
                format=result.get("format", "raw"),
                bytes_size=result.get("bytes", 0),
                created_at=result.get("created_at", ""),
            )
        except Exception as exc:
            RAG_STORAGE_UPLOAD_DURATION.observe(time.monotonic() - t0)
            RAG_STORAGE_UPLOAD_TOTAL.labels(status="error").inc()
            logger.error("rag.storage.upload_failed", error=str(exc))
            raise

    def signed_url(self, public_id: str, *, expires_in_seconds: int = 3600) -> str:
        """Return a time-limited signed URL for a private raw asset."""
        import time as _time

        expire_at = int(_time.time()) + expires_in_seconds
        url, _ = self._utils.cloudinary_url(
            public_id,
            resource_type="raw",
            sign_url=True,
            expires_at=expire_at,
        )
        return url

    async def download(self, public_id: str) -> bytes:
        """Stream raw file bytes from Cloudinary for ingestion processing."""
        import httpx

        url = self.signed_url(public_id)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


def get_cloudinary_client() -> "CloudinaryClient | None":
    """Return a CloudinaryClient configured from agent_settings, or None if not set.

    Use this factory everywhere instead of constructing CloudinaryClient directly
    so the credentials come from the environment, not hardcoded args.
    """
    from agents.config import agent_settings  # local import avoids circular deps

    cloud_name = agent_settings.cloudinary_cloud_name
    api_key = agent_settings.cloudinary_api_key
    api_secret = agent_settings.cloudinary_api_secret
    if not (cloud_name and api_key and api_secret):
        return None
    return CloudinaryClient(
        cloud_name=cloud_name,
        api_key=api_key.get_secret_value(),
        api_secret=api_secret.get_secret_value(),
        upload_folder=agent_settings.cloudinary_upload_folder,
    )
