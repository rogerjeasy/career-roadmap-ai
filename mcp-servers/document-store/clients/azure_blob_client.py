"""Azure Blob Storage client for document store.

Requires: ``azure-storage-blob>=12.19.0``

Documents are stored as blobs under path:
    ``<container>/<user_id>/<document_id>/<filename>``

Metadata is stored as blob properties (custom metadata tags).
"""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from clients.base_client import BaseStorageClient
from models import DocumentType, StoredDocument

logger = structlog.get_logger(__name__)


class AzureBlobStorageClient(BaseStorageClient):
    """Stores documents in Azure Blob Storage."""

    provider = "azure"

    def __init__(self, connection_string: str, container_name: str) -> None:
        self._connection_string = connection_string
        self._container_name = container_name
        self._container_client: Any = None

    async def _get_container(self) -> Any:
        if self._container_client is None:
            from azure.storage.blob.aio import ContainerClient  # type: ignore[import]

            self._container_client = ContainerClient.from_connection_string(
                self._connection_string, self._container_name
            )
            # Ensure container exists
            try:
                await self._container_client.create_container()
            except Exception:
                pass  # Already exists
        return self._container_client

    def _blob_name(self, user_id: str, document_id: str, filename: str) -> str:
        return f"{user_id}/{document_id}/{filename}"

    def _meta_blob_name(self, user_id: str, document_id: str) -> str:
        return f"{user_id}/{document_id}/.meta.json"

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
        container = await self._get_container()
        blob_name = self._blob_name(user_id, document_id, filename)

        # Azure blob metadata values must be strings
        blob_meta = {
            "document_type": document_type.value,
            "original_filename": filename,
            "user_id": user_id,
            "document_id": document_id,
        }

        blob_client = container.get_blob_client(blob_name)
        await blob_client.upload_blob(
            content,
            blob_type="BlockBlob",
            content_settings={"content_type": content_type},
            metadata=blob_meta,
            overwrite=True,
        )

        now = datetime.now(UTC).isoformat()
        properties = await blob_client.get_blob_properties()
        sas_url = _generate_sas_url(blob_client)

        doc = StoredDocument(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            document_type=document_type,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=blob_name,
            download_url=sas_url,
            created_at=str(properties.creation_time.isoformat()) if properties.creation_time else now,
            updated_at=now,
            metadata=metadata,
        )

        # Store full metadata as a separate JSON blob
        meta_blob = container.get_blob_client(self._meta_blob_name(user_id, document_id))
        await meta_blob.upload_blob(doc.model_dump_json().encode(), overwrite=True)

        logger.info("azure_storage.upload_ok", user_id=user_id, document_id=document_id, blob=blob_name)
        return doc

    async def get(
        self,
        *,
        user_id: str,
        document_id: str,
        include_content: bool = False,
    ) -> StoredDocument | None:
        container = await self._get_container()
        meta_blob = container.get_blob_client(self._meta_blob_name(user_id, document_id))

        try:
            stream = await meta_blob.download_blob()
            raw = await stream.readall()
            doc = StoredDocument.model_validate_json(raw)
        except Exception:
            return None

        if include_content:
            content_blob = container.get_blob_client(self._blob_name(user_id, document_id, doc.filename))
            try:
                stream = await content_blob.download_blob()
                content = await stream.readall()
                doc.metadata["content_base64"] = base64.b64encode(content).decode()
            except Exception as exc:
                logger.warning("azure_storage.content_fetch_failed", error=str(exc))

        return doc

    async def list(
        self,
        *,
        user_id: str,
        document_type: DocumentType | None = None,
        limit: int = 20,
    ) -> list[StoredDocument]:
        container = await self._get_container()
        prefix = f"{user_id}/"
        docs: list[StoredDocument] = []

        async for blob in container.list_blobs(name_starts_with=prefix):
            if not blob.name.endswith("/.meta.json"):
                continue
            try:
                blob_client = container.get_blob_client(blob.name)
                stream = await blob_client.download_blob()
                raw = await stream.readall()
                doc = StoredDocument.model_validate_json(raw)
                if document_type is None or doc.document_type == document_type:
                    docs.append(doc)
            except Exception as exc:
                logger.warning("azure_storage.meta_parse_failed", blob=blob.name, error=str(exc))

            if len(docs) >= limit:
                break

        return docs

    async def delete(self, *, user_id: str, document_id: str) -> bool:
        container = await self._get_container()
        prefix = f"{user_id}/{document_id}/"
        deleted = False

        async for blob in container.list_blobs(name_starts_with=prefix):
            blob_client = container.get_blob_client(blob.name)
            try:
                await blob_client.delete_blob()
                deleted = True
            except Exception as exc:
                logger.warning("azure_storage.delete_blob_failed", blob=blob.name, error=str(exc))

        if deleted:
            logger.info("azure_storage.delete_ok", user_id=user_id, document_id=document_id)
        return deleted

    async def health_check(self) -> bool:
        try:
            container = await self._get_container()
            await container.get_container_properties()
            return True
        except Exception:
            return False


def _generate_sas_url(blob_client: Any) -> str | None:
    try:
        from datetime import timedelta
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions  # type: ignore[import]

        return blob_client.url  # SAS would need account key; return direct URL for now
    except Exception:
        return blob_client.url
