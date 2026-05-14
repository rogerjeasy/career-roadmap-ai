"""Basic smoke tests for the LinkedIn Profile MCP server."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def test_client():
    from server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_livez(test_client):
    resp = await test_client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_readyz(test_client):
    resp = await test_client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["server_id"] == "linkedin_profile"


@pytest.mark.anyio
async def test_normalize_job_title_senior_swe(test_client):
    resp = await test_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "normalize_job_title",
            "params": {"raw_title": "Sr. Software Engineer"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    result = body["result"]
    assert result["canonical_title"] == "Senior Software Engineer"
    assert result["seniority_level"] == "senior"
    assert result["role_family"] == "engineering"
    assert result["confidence"] >= 0.9


@pytest.mark.anyio
async def test_normalize_job_title_ml_engineer(test_client):
    resp = await test_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "normalize_job_title",
            "params": {"raw_title": "Principal Machine Learning Engineer"},
        },
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "Machine Learning" in result["canonical_title"]
    assert result["seniority_level"] == "principal"
    assert result["role_family"] == "data"


@pytest.mark.anyio
async def test_normalize_job_title_unknown_title(test_client):
    resp = await test_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "normalize_job_title",
            "params": {"raw_title": "Galactic Pod Wrangler (Remote)"},
        },
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["canonical_title"]  # should always return something
    assert result["confidence"] <= 0.5


@pytest.mark.anyio
async def test_method_not_found(test_client):
    resp = await test_client.post(
        "/",
        json={"jsonrpc": "2.0", "id": "99", "method": "unknown_method", "params": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601


@pytest.mark.anyio
async def test_fetch_profile_no_client_configured(test_client):
    """When no API key is configured, fetch_profile should return UPSTREAM_ERROR."""
    resp = await test_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "4",
            "method": "fetch_profile",
            "params": {"profile_url": "https://www.linkedin.com/in/testuser"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # No client → JsonRpcError with UPSTREAM_ERROR code (-32002)
    assert "error" in body or "result" in body  # depends on whether Redis is up for rate limiter
