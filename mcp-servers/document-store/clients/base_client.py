"""Abstract base client for document storage providers."""
from __future__ import annotations

import abc
from typing import Any

from models import DocumentType, StoredDocument


class BaseStorageClient(abc.ABC):
    """Abstract storage client. Subclasses implement provider-specific logic."""

    provider: str = "unknown"

    @abc.abstractmethod
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
        """Store *content* and return a StoredDocument record. Raises on failure."""
        ...

    @abc.abstractmethod
    async def get(
        self,
        *,
        user_id: str,
        document_id: str,
        include_content: bool = False,
    ) -> StoredDocument | None:
        """Return document metadata (and optionally content). None if not found."""
        ...

    @abc.abstractmethod
    async def list(
        self,
        *,
        user_id: str,
        document_type: DocumentType | None = None,
        limit: int = 20,
    ) -> list[StoredDocument]:
        """List documents for *user_id*, optionally filtered by *document_type*."""
        ...

    @abc.abstractmethod
    async def delete(self, *, user_id: str, document_id: str) -> bool:
        """Delete a document. Returns True if deleted, False if not found."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the storage backend is reachable."""
        ...
