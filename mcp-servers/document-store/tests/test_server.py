"""Integration tests for Document Store MCP server."""
from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── helpers ───────────────────────────────────────────────────────────────────

def rpc(method: str, params: dict[str, Any], req_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}


_HEADERS = {
    "X-MCP-API-Key": "test-api-key",
    "X-User-ID": "user-abc",
    "X-Correlation-ID": "test-corr-123",
}


# ── liveness / readiness ──────────────────────────────────────────────────────

async def test_livez(client: AsyncClient) -> None:
    resp = await client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readyz_healthy(client: AsyncClient, mock_storage: AsyncMock) -> None:
    mock_storage.health_check.return_value = True
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["storage"] == "ok"


async def test_readyz_storage_unhealthy(client: AsyncClient, mock_storage: AsyncMock) -> None:
    mock_storage.health_check.return_value = False
    resp = await client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["storage"] == "error"


# ── upload_document ───────────────────────────────────────────────────────────

async def test_upload_document_success(client: AsyncClient, pdf_b64: str) -> None:
    payload = rpc("upload_document", {
        "user_id": "user-abc",
        "filename": "resume.pdf",
        "document_type": "cv",
        "content_type": "application/pdf",
        "content_base64": pdf_b64,
        "metadata": {"language": "en"},
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["uploaded"] is True
    assert "document" in body["result"]


async def test_upload_document_invalid_base64(client: AsyncClient) -> None:
    payload = rpc("upload_document", {
        "user_id": "user-abc",
        "filename": "resume.pdf",
        "document_type": "cv",
        "content_base64": "!!!not-base64!!!",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


async def test_upload_document_too_large(client: AsyncClient) -> None:
    big = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
    payload = rpc("upload_document", {
        "user_id": "user-abc",
        "filename": "huge.pdf",
        "document_type": "cv",
        "content_base64": big,
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602


async def test_upload_document_limit_reached(
    client: AsyncClient, mock_storage: AsyncMock, pdf_b64: str
) -> None:
    from models import DocumentType, StoredDocument

    mock_storage.list.return_value = [
        StoredDocument(
            document_id=f"doc-{i}", user_id="user-abc", filename="f.pdf",
            document_type=DocumentType.CV, content_type="application/pdf",
            size_bytes=100, storage_path="local://x", created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        for i in range(20)
    ]
    payload = rpc("upload_document", {
        "user_id": "user-abc",
        "filename": "resume.pdf",
        "document_type": "cv",
        "content_base64": pdf_b64,
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert "limit" in body["error"]["message"].lower()


# ── get_document ──────────────────────────────────────────────────────────────

async def test_get_document_success(client: AsyncClient) -> None:
    payload = rpc("get_document", {
        "user_id": "user-abc",
        "document_id": "doc-001",
        "include_content": False,
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "document" in body["result"]
    assert body["result"]["document"]["document_id"] == "doc-001"


async def test_get_document_not_found(client: AsyncClient, mock_storage: AsyncMock) -> None:
    mock_storage.get.return_value = None
    payload = rpc("get_document", {
        "user_id": "user-abc",
        "document_id": "doc-missing",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert "not found" in body["error"]["message"].lower()


# ── list_documents ────────────────────────────────────────────────────────────

async def test_list_documents_success(client: AsyncClient) -> None:
    payload = rpc("list_documents", {
        "user_id": "user-abc",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["total_count"] == 1
    assert body["result"]["user_id"] == "user-abc"
    assert len(body["result"]["documents"]) == 1


async def test_list_documents_filtered_by_type(
    client: AsyncClient, mock_storage: AsyncMock
) -> None:
    mock_storage.list.return_value = []
    payload = rpc("list_documents", {
        "user_id": "user-abc",
        "document_type": "certificate",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["total_count"] == 0


# ── delete_document ───────────────────────────────────────────────────────────

async def test_delete_document_success(client: AsyncClient) -> None:
    payload = rpc("delete_document", {
        "user_id": "user-abc",
        "document_id": "doc-001",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["deleted"] is True
    assert body["result"]["document_id"] == "doc-001"


async def test_delete_document_not_found(client: AsyncClient, mock_storage: AsyncMock) -> None:
    mock_storage.delete.return_value = False
    payload = rpc("delete_document", {
        "user_id": "user-abc",
        "document_id": "doc-missing",
    })
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert "not found" in body["error"]["message"].lower()


# ── rate limiting ─────────────────────────────────────────────────────────────

async def test_rate_limit_enforced(client: AsyncClient, mock_rate_limiter: AsyncMock) -> None:
    mock_rate_limiter.check.return_value = False
    payload = rpc("list_documents", {"user_id": "user-abc"})
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert "rate limit" in body["error"]["message"].lower()


# ── unknown method ────────────────────────────────────────────────────────────

async def test_unknown_method(client: AsyncClient) -> None:
    payload = rpc("unknown_tool", {"user_id": "user-abc"})
    resp = await client.post("/", json=payload, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


# ── invalid JSON-RPC envelope ─────────────────────────────────────────────────

async def test_missing_method_field(client: AsyncClient) -> None:
    resp = await client.post("/", json={"jsonrpc": "2.0", "id": 1}, headers=_HEADERS)
    assert resp.status_code == 200
    assert "error" in resp.json()


async def test_non_json_body(client: AsyncClient) -> None:
    resp = await client.post(
        "/",
        content="not json",
        headers={**_HEADERS, "content-type": "application/json"},
    )
    assert resp.status_code in (200, 400, 422)
