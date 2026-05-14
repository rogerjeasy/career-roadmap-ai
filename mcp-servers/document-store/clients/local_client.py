"""Local filesystem storage client (development / fallback).

Stores files under ``<base_path>/<user_id>/<document_id>/<filename>`` and keeps
a JSON sidecar ``<document_id>.meta.json`` with the StoredDocument metadata.
No external dependencies required — always available.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import aiofiles
import structlog

from clients.base_client import BaseStorageClient
from models import DocumentType, StoredDocument

logger = structlog.get_logger(__name__)


class LocalStorageClient(BaseStorageClient):
    """Stores documents on the local filesystem."""

    provider = "local"

    def __init__(self, base_path: str) -> None:
        self._base_path = os.path.abspath(base_path)
        os.makedirs(self._base_path, exist_ok=True)

    def _user_dir(self, user_id: str) -> str:
        # Sanitize to prevent path traversal
        safe = user_id.replace("/", "_").replace("..", "_")
        return os.path.join(self._base_path, safe)

    def _doc_dir(self, user_id: str, document_id: str) -> str:
        return os.path.join(self._user_dir(user_id), document_id)

    def _meta_path(self, user_id: str, document_id: str) -> str:
        return os.path.join(self._doc_dir(user_id, document_id), "meta.json")

    def _content_path(self, user_id: str, document_id: str, filename: str) -> str:
        return os.path.join(self._doc_dir(user_id, document_id), filename)

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
        doc_dir = self._doc_dir(user_id, document_id)
        await asyncio.to_thread(os.makedirs, doc_dir, exist_ok=True)

        content_path = self._content_path(user_id, document_id, filename)
        async with aiofiles.open(content_path, "wb") as f:
            await f.write(content)

        now = datetime.now(UTC).isoformat()
        doc = StoredDocument(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            document_type=document_type,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=content_path,
            download_url=None,  # No public URL for local storage
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

        async with aiofiles.open(self._meta_path(user_id, document_id), "w") as f:
            await f.write(doc.model_dump_json())

        logger.info(
            "local_storage.upload_ok",
            user_id=user_id,
            document_id=document_id,
            size_bytes=len(content),
        )
        return doc

    async def get(
        self,
        *,
        user_id: str,
        document_id: str,
        include_content: bool = False,
    ) -> StoredDocument | None:
        meta_path = self._meta_path(user_id, document_id)
        if not await asyncio.to_thread(os.path.exists, meta_path):
            return None

        async with aiofiles.open(meta_path) as f:
            raw = await f.read()

        doc = StoredDocument.model_validate_json(raw)

        if include_content:
            content_path = doc.storage_path
            if await asyncio.to_thread(os.path.exists, content_path):
                async with aiofiles.open(content_path, "rb") as f:
                    content = await f.read()
                import base64
                doc.metadata["content_base64"] = base64.b64encode(content).decode()

        return doc

    async def list(
        self,
        *,
        user_id: str,
        document_type: DocumentType | None = None,
        limit: int = 20,
    ) -> list[StoredDocument]:
        user_dir = self._user_dir(user_id)
        if not await asyncio.to_thread(os.path.exists, user_dir):
            return []

        entries = await asyncio.to_thread(os.listdir, user_dir)
        docs: list[StoredDocument] = []

        for entry in sorted(entries):
            meta_path = os.path.join(user_dir, entry, "meta.json")
            if not await asyncio.to_thread(os.path.exists, meta_path):
                continue
            try:
                async with aiofiles.open(meta_path) as f:
                    raw = await f.read()
                doc = StoredDocument.model_validate_json(raw)
                if document_type is None or doc.document_type == document_type:
                    docs.append(doc)
            except Exception as exc:
                logger.warning("local_storage.meta_parse_failed", path=meta_path, error=str(exc))

            if len(docs) >= limit:
                break

        return docs

    async def delete(self, *, user_id: str, document_id: str) -> bool:
        doc_dir = self._doc_dir(user_id, document_id)
        if not await asyncio.to_thread(os.path.exists, doc_dir):
            return False

        import shutil
        await asyncio.to_thread(shutil.rmtree, doc_dir, ignore_errors=True)
        logger.info("local_storage.delete_ok", user_id=user_id, document_id=document_id)
        return True

    async def health_check(self) -> bool:
        return await asyncio.to_thread(os.path.isdir, self._base_path)
