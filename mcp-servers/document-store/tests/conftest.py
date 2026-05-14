"""Shared pytest fixtures for document-store tests."""
from __future__ import annotations

import base64
import os
import tempfile
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MCP_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("BLOB_STORAGE_PROVIDER", "local")
os.environ.setdefault("LOCAL_STORAGE_BASE_PATH", tempfile.mkdtemp())
os.environ.setdefault("MCP_API_KEY", "test-api-key")


from models import DocumentType, StoredDocument  # noqa: E402


def _make_stored_document(
    document_id: str = "doc-001",
    user_id: str = "user-abc",
    filename: str = "resume.pdf",
    document_type: DocumentType = DocumentType.CV,
    size_bytes: int = 1024,
) -> StoredDocument:
    return StoredDocument(
        document_id=document_id,
        user_id=user_id,
        filename=filename,
        document_type=document_type,
        content_type="application/pdf",
        size_bytes=size_bytes,
        storage_path=f"local://{user_id}/{document_id}/{filename}",
        download_url=None,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )


@pytest.fixture()
def sample_doc() -> StoredDocument:
    return _make_stored_document()


@pytest.fixture()
def mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.provider = "local"
    storage.health_check = AsyncMock(return_value=True)
    storage.upload = AsyncMock(return_value=_make_stored_document())
    storage.get = AsyncMock(return_value=_make_stored_document())
    storage.list = AsyncMock(return_value=[_make_stored_document()])
    storage.delete = AsyncMock(return_value=True)
    return storage


@pytest.fixture()
def mock_rate_limiter() -> AsyncMock:
    rl = AsyncMock()
    rl.check = AsyncMock(return_value=True)
    return rl


def _small_pdf_b64() -> str:
    return base64.b64encode(b"%PDF-1.4 fake content").decode()


@pytest.fixture()
def pdf_b64() -> str:
    return _small_pdf_b64()


@pytest_asyncio.fixture()
async def client(mock_storage: AsyncMock, mock_rate_limiter: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired to the FastAPI app with mocked storage + rate limiter."""
    from server import create_app  # noqa: PLC0415

    app = create_app(storage=mock_storage, rate_limiter=mock_rate_limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
