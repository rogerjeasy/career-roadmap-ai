"""Tests for the Job Board MCP Server.

Uses ``pytest-asyncio`` and ``httpx.AsyncClient`` to drive the FastAPI app
in-process — no network calls are made.

All job board clients are replaced with stubs that return controlled data,
keeping tests fast and deterministic.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from models import (
    JobPosting,
    JobSource,
    SearchJobsParams,
    TrendingRole,
)

# ---------------------------------------------------------------------------
# Stub client factory
# ---------------------------------------------------------------------------


def _make_posting(
    title: str = "Software Engineer",
    company: str = "TechCorp AG",
    source: JobSource = JobSource.LINKEDIN,
) -> JobPosting:
    return JobPosting(
        id=f"test-{title[:4].lower()}",
        title=title,
        company=company,
        location="Zurich, Switzerland",
        country="CH",
        remote=False,
        required_skills=["Python", "Docker", "Kubernetes"],
        salary_min=100_000,
        salary_max=130_000,
        currency="CHF",
        source=source,
        source_url="https://example.com/job/1",
        posted_date=date.today(),
    )


class _StubClient:
    def __init__(self, source: JobSource, postings: list[JobPosting] | None = None) -> None:
        self.source = source
        self._postings = postings or [_make_posting(source=source)]

    async def search(self, params: SearchJobsParams, *, correlation_id: str = "") -> list[JobPosting]:
        return self._postings

    async def get_detail(self, job_id: str, *, correlation_id: str = "") -> JobPosting | None:
        return next((p for p in self._postings if p.id == job_id), None)

    async def get_trending_roles(
        self, country: str, limit: int, *, correlation_id: str = ""
    ) -> list[TrendingRole]:
        return [
            TrendingRole(
                title="Software Engineer",
                posting_count=500,
                growth_percent=12.5,
                top_skills=["Python", "Docker"],
                country=country,
                sources=[self.source],
            )
        ]


# ---------------------------------------------------------------------------
# App fixture with stubbed dependencies
# ---------------------------------------------------------------------------


@pytest.fixture()
def stub_clients() -> dict[str, _StubClient]:
    return {
        "linkedin": _StubClient(JobSource.LINKEDIN, [_make_posting(source=JobSource.LINKEDIN)]),
        "swiss_jobs": _StubClient(
            JobSource.SWISS_JOBS, [_make_posting(source=JobSource.SWISS_JOBS)]
        ),
    }


@pytest.fixture()
def stub_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture()
def stub_rate_limiter():
    limiter = MagicMock()
    limiter.check = AsyncMock(return_value=True)
    return limiter


@pytest.fixture()
def test_client(stub_clients, stub_cache, stub_rate_limiter):
    """Returns a TestClient with all external dependencies stubbed out."""
    import server as srv

    original_clients = srv._clients
    original_cache = srv._cache
    original_rate_limiter = srv._rate_limiter

    srv._clients = stub_clients
    srv._cache = stub_cache
    srv._rate_limiter = stub_rate_limiter

    with TestClient(srv.app, raise_server_exceptions=False) as client:
        yield client

    srv._clients = original_clients
    srv._cache = original_cache
    srv._rate_limiter = original_rate_limiter


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_livez(test_client):
    resp = test_client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz(test_client):
    resp = test_client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["server_id"] == "job_board"
    assert isinstance(body["sources"], list)


def test_metrics_endpoint(test_client):
    resp = test_client.get("/metrics")
    assert resp.status_code == 200
    assert b"mcp_job_board" in resp.content or b"python_gc" in resp.content


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------


def _rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": "test-1", "method": method, "params": params}


def test_parse_error_returns_rpc_error(test_client):
    resp = test_client.post("/", content=b"not-json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32700  # PARSE_ERROR


def test_method_not_found(test_client):
    resp = test_client.post("/", json=_rpc("unknown_method", {}))
    body = resp.json()
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_invalid_request_missing_jsonrpc(test_client):
    resp = test_client.post("/", json={"id": "1", "method": "search_jobs", "params": {}})
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32600  # INVALID_REQUEST


# ---------------------------------------------------------------------------
# search_jobs
# ---------------------------------------------------------------------------


def test_search_jobs_valid_request(test_client):
    payload = _rpc("search_jobs", {"role": "Software Engineer", "country": "CH", "limit": 5})
    resp = test_client.post("/", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    result = body["result"]
    assert "postings" in result
    assert isinstance(result["postings"], list)
    assert "total_count" in result
    assert "sources_queried" in result


def test_search_jobs_invalid_params(test_client):
    payload = _rpc("search_jobs", {"role": "", "country": "CH"})  # role too short
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


def test_search_jobs_returns_normalised_fields(test_client):
    payload = _rpc("search_jobs", {"role": "Data Engineer", "country": "CH"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    postings = body["result"]["postings"]
    if postings:
        posting = postings[0]
        assert "title" in posting
        assert "company" in posting
        assert "required_skills" in posting
        assert isinstance(posting["required_skills"], list)


def test_search_jobs_cache_hit(test_client, stub_cache):
    """When cache returns data, the tool returns it without calling clients."""
    cached_result = {
        "postings": [],
        "total_count": 0,
        "sources_queried": ["LinkedIn"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    stub_cache.get = AsyncMock(return_value=cached_result)

    payload = _rpc("search_jobs", {"role": "Software Engineer", "country": "CH"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    assert body["result"]["total_count"] == 0


def test_search_jobs_rate_limited(test_client, stub_rate_limiter):
    from shared.error_handler import JsonRpcErrorCode

    stub_rate_limiter.check = AsyncMock(return_value=False)
    payload = _rpc("search_jobs", {"role": "Engineer", "country": "CH"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == int(JsonRpcErrorCode.RATE_LIMITED)


# ---------------------------------------------------------------------------
# get_job_detail
# ---------------------------------------------------------------------------


def test_get_job_detail_valid(test_client, stub_clients):
    # The stub LinkedIn client has one posting with id "test-soft"
    posting_id = stub_clients["linkedin"]._postings[0].id
    payload = _rpc("get_job_detail", {"job_id": posting_id, "source": "LinkedIn"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    assert body["result"]["id"] == posting_id


def test_get_job_detail_not_found(test_client):
    payload = _rpc("get_job_detail", {"job_id": "nonexistent-999", "source": "LinkedIn"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND (job not found)


def test_get_job_detail_invalid_params(test_client):
    payload = _rpc("get_job_detail", {"job_id": ""})  # missing source
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# get_trending_roles
# ---------------------------------------------------------------------------


def test_get_trending_roles_valid(test_client):
    payload = _rpc("get_trending_roles", {"country": "CH", "limit": 5})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    result = body["result"]
    assert "trending_roles" in result
    assert isinstance(result["trending_roles"], list)
    assert result["country"] == "CH"


def test_get_trending_roles_invalid_country(test_client):
    payload = _rpc("get_trending_roles", {"country": "ZZZ"})  # country too long
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


def test_get_trending_roles_merges_sources(test_client):
    payload = _rpc("get_trending_roles", {"country": "CH", "limit": 10})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    result = body["result"]
    assert len(result["trending_roles"]) > 0
    first = result["trending_roles"][0]
    assert "title" in first
    assert "posting_count" in first
    assert "top_skills" in first


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


def test_job_posting_deduplicates_skills():
    p = JobPosting(
        id="x",
        title="Engineer",
        company="Co",
        location="Zurich",
        required_skills=["Python", "python", "PYTHON", "Docker"],
        source=JobSource.LINKEDIN,
    )
    assert len(p.required_skills) == 2
    assert "Python" in p.required_skills
    assert "Docker" in p.required_skills


def test_job_posting_model_dump_api_shape():
    p = _make_posting()
    api_dict = p.model_dump_api()
    expected_keys = {
        "id", "title", "company", "location", "country", "remote",
        "employment_type", "experience_level", "required_skills",
        "nice_to_have_skills", "salary_min", "salary_max", "currency",
        "source", "url", "apply_url", "posted_date", "fetched_at",
    }
    assert expected_keys.issubset(api_dict.keys())
