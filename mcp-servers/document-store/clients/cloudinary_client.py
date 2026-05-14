"""Cloudinary storage client for document store.

Documents are stored as raw assets:
    Content:  cloudinary://career-roadmap/documents/<user_id>/<document_id>/<filename>
    Metadata: cloudinary://career-roadmap/documents/<user_id>/<document_id>/.meta
              (a raw JSON file — StoredDocument model serialised to bytes)

The Cloudinary SDK uses a module-level config singleton; construct only one
instance per process (the lifespan does this).
"""
from __future__ import annotations

import asyncio
import base64
import io
import time as _time
from datetime import UTC, datetime
from typing import Any

import structlog

from clients.base_client import BaseStorageClient
from models import DocumentType, StoredDocument

logger = structlog.get_logger(__name__)


class CloudinaryStorageClient(BaseStorageClient):
    """Stores documents as raw Cloudinary assets with a JSON metadata sidecar."""

    provider = "cloudinary"

    def __init__(
        self,
        *,
        cloud_name: str,
        api_key: str,
        api_secret: str,
        upload_folder: str = "career-roadmap/documents",
    ) -> None:
        try:
            import cloudinary  # type: ignore[import-untyped]
            import cloudinary.api  # type: ignore[import-untyped]
            import cloudinary.uploader  # type: ignore[import-untyped]
            import cloudinary.utils  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "cloudinary package is required. Add cloudinary>=1.40.0 to pyproject.toml"
            ) from exc

        self._cloudinary = cloudinary
        self._api = cloudinary.api
        self._uploader = cloudinary.uploader
        self._utils = cloudinary.utils

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        self._folder = upload_folder

    # ── Public ID helpers ──────────────────────────────────────────────────────

    def _content_pid(self, user_id: str, document_id: str, filename: str) -> str:
        return f"{self._folder}/{user_id}/{document_id}/{filename}"

    def _meta_pid(self, user_id: str, document_id: str) -> str:
        return f"{self._folder}/{user_id}/{document_id}/.meta"

    def _signed_url(self, public_id: str, *, expires_in: int = 3600) -> str:
        expire_at = int(_time.time()) + expires_in
        url, _ = self._utils.cloudinary_url(
            public_id,
            resource_type="raw",
            sign_url=True,
            expires_at=expire_at,
        )
        return url

    # ── BaseStorageClient interface ────────────────────────────────────────────

    async def upload(
        self,
        *,
        user_id: str,
        document_id: str,
        filename: str,
        document_type: DocumentType,
        content_type: str,
        content: bytes,
        metadata: dict[str, Any],
    ) -> StoredDocument:
        content_pid = self._content_pid(user_id, document_id, filename)

        result = await asyncio.to_thread(
            self._uploader.upload,
            io.BytesIO(content),
            public_id=content_pid,
            resource_type="raw",
            overwrite=True,
            tags=[f"user:{user_id}", f"doc_type:{document_type.value}"],
        )

        now = datetime.now(UTC).isoformat()
        doc = StoredDocument(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            document_type=document_type,
            content_type=content_type,
            size_bytes=result.get("bytes", len(content)),
            storage_path=f"cloudinary://{self._cloudinary.config().cloud_name}/{content_pid}",
            download_url=self._signed_url(content_pid),
            created_at=result.get("created_at", now),
            updated_at=now,
            metadata=metadata,
        )

        # Store metadata as a sidecar raw file so it survives process restarts
        await asyncio.to_thread(
            self._uploader.upload,
            io.BytesIO(doc.model_dump_json().encode()),
            public_id=self._meta_pid(user_id, document_id),
            resource_type="raw",
            overwrite=True,
        )

        logger.info(
            "cloudinary_storage.upload_ok",
            user_id=user_id,
            document_id=document_id,
            size_bytes=doc.size_bytes,
        )
        return doc

    async def get(
        self,
        *,
        user_id: str,
        document_id: str,
        include_content: bool = False,
    ) -> StoredDocument | None:
        import httpx

        meta_url = self._signed_url(self._meta_pid(user_id, document_id))
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.get(meta_url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                doc = StoredDocument.model_validate_json(resp.content)
        except Exception as exc:
            logger.warning("cloudinary_storage.meta_fetch_failed", error=str(exc))
            return None

        if include_content:
            content_url = self._signed_url(self._content_pid(user_id, document_id, doc.filename))
            try:
                async with httpx.AsyncClient(timeout=60.0) as http:
                    resp = await http.get(content_url)
                    resp.raise_for_status()
                    doc.metadata["content_base64"] = base64.b64encode(resp.content).decode()
            except Exception as exc:
                logger.warning("cloudinary_storage.content_fetch_failed", error=str(exc))

        return doc

    async def list(
        self,
        *,
        user_id: str,
        document_type: DocumentType | None = None,
        limit: int = 20,
    ) -> list[StoredDocument]:
        import httpx

        prefix = f"{self._folder}/{user_id}/"
        try:
            # Fetch all raw resources under the user's folder prefix.
            # Multiply limit so filtering for .meta still returns enough results.
            result = await asyncio.to_thread(
                self._api.resources,
                type="upload",
                resource_type="raw",
                prefix=prefix,
                max_results=min(limit * 3, 500),
            )
        except Exception as exc:
            logger.warning("cloudinary_storage.list_failed", user_id=user_id, error=str(exc))
            return []

        meta_resources = [
            r for r in result.get("resources", [])
            if r["public_id"].endswith("/.meta")
        ]

        docs: list[StoredDocument] = []
        async with httpx.AsyncClient(timeout=15.0) as http:
            for resource in meta_resources[:limit]:
                meta_url = self._signed_url(resource["public_id"])
                try:
                    resp = await http.get(meta_url)
                    resp.raise_for_status()
                    doc = StoredDocument.model_validate_json(resp.content)
                    if document_type is None or doc.document_type == document_type:
                        docs.append(doc)
                except Exception as exc:
                    logger.warning(
                        "cloudinary_storage.meta_parse_failed",
                        public_id=resource["public_id"],
                        error=str(exc),
                    )

        return docs

    async def delete(self, *, user_id: str, document_id: str) -> bool:
        doc = await self.get(user_id=user_id, document_id=document_id)
        if doc is None:
            return False

        content_pid = self._content_pid(user_id, document_id, doc.filename)
        meta_pid = self._meta_pid(user_id, document_id)

        await asyncio.to_thread(
            self._api.delete_resources,
            [content_pid, meta_pid],
            resource_type="raw",
            invalidate=True,
        )
        logger.info("cloudinary_storage.delete_ok", user_id=user_id, document_id=document_id)
        return True

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._api.ping)
            return True
        except Exception:
            return False
