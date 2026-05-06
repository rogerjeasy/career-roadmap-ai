"""Tests for the Course Catalogue MCP Server.

Uses ``pytest-asyncio`` and FastAPI's ``TestClient`` in-process — no network calls.

All course clients are replaced with stubs that return controlled data,
keeping tests fast and deterministic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from models import Course, CourseSource, SearchCoursesParams, SkillLevel

# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


def _make_course(
    title: str = "Python for Beginners",
    platform: CourseSource = CourseSource.COURSERA,
    free: bool = True,
) -> Course:
    return Course(
        id=f"test-{title[:6].lower().replace(' ', '-')}",
        title=title,
        platform=platform,
        instructor="Test Instructor",
        url=f"https://example.com/course/{title[:4].lower()}",
        description="A comprehensive course on the topic.",
        skills=["Python", "Programming"],
        skill_level=SkillLevel.BEGINNER,
        duration_hours=10.5,
        rating=4.7,
        num_ratings=1500,
        free=free,
        language="en",
        certificate=True,
    )


class _StubClient:
    def __init__(
        self,
        source: CourseSource,
        courses: list[Course] | None = None,
    ) -> None:
        self.source = source
        self._courses = courses or [_make_course(platform=source)]

    async def search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        return self._courses

    async def get_detail(self, course_id: str, *, correlation_id: str = "") -> Course | None:
        return next((c for c in self._courses if c.id == course_id), None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def stub_clients() -> dict[str, _StubClient]:
    return {
        "coursera": _StubClient(
            CourseSource.COURSERA,
            [_make_course("Python Fundamentals", CourseSource.COURSERA)],
        ),
        "edx": _StubClient(
            CourseSource.EDX,
            [_make_course("Data Science Basics", CourseSource.EDX)],
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
    assert body["server_id"] == "course_catalogue"
    assert isinstance(body["sources"], list)


def test_metrics_endpoint(test_client):
    resp = test_client.get("/metrics")
    assert resp.status_code == 200
    assert b"mcp_course_catalogue" in resp.content or b"python_gc" in resp.content


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
    resp = test_client.post("/", json={"id": "1", "method": "search_courses", "params": {}})
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32600  # INVALID_REQUEST


# ---------------------------------------------------------------------------
# search_courses
# ---------------------------------------------------------------------------


def test_search_courses_valid_request(test_client):
    payload = _rpc("search_courses", {"skill": "Python", "level": "beginner", "limit": 5})
    resp = test_client.post("/", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    result = body["result"]
    assert "courses" in result
    assert isinstance(result["courses"], list)
    assert "total_count" in result
    assert "sources_queried" in result


def test_search_courses_invalid_params(test_client):
    payload = _rpc("search_courses", {"skill": "", "level": "beginner"})  # skill too short
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


def test_search_courses_returns_normalised_fields(test_client):
    payload = _rpc("search_courses", {"skill": "Machine Learning"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    courses = body["result"]["courses"]
    if courses:
        course = courses[0]
        assert "title" in course
        assert "platform" in course
        assert "url" in course
        assert "free" in course
        assert "skills" in course
        assert isinstance(course["skills"], list)


def test_search_courses_cache_hit(test_client, stub_cache):
    cached_result = {
        "courses": [],
        "total_count": 0,
        "sources_queried": ["Coursera"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    stub_cache.get = AsyncMock(return_value=cached_result)

    payload = _rpc("search_courses", {"skill": "Docker"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    assert body["result"]["total_count"] == 0


def test_search_courses_rate_limited(test_client, stub_rate_limiter):
    from shared.error_handler import JsonRpcErrorCode

    stub_rate_limiter.check = AsyncMock(return_value=False)
    payload = _rpc("search_courses", {"skill": "Kubernetes"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == int(JsonRpcErrorCode.RATE_LIMITED)


def test_search_courses_free_only_filter(test_client, stub_clients):
    # Add a paid course to the stub
    paid_course = _make_course("Paid Course", CourseSource.UDEMY, free=False)
    stub_clients["udemy"] = _StubClient(CourseSource.UDEMY, [paid_course])

    payload = _rpc("search_courses", {"skill": "Python", "free_only": True})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    # Paid courses from udemy should not appear
    courses = body["result"]["courses"]
    for course in courses:
        assert course["free"] is True


# ---------------------------------------------------------------------------
# get_course_detail
# ---------------------------------------------------------------------------


def test_get_course_detail_valid(test_client, stub_clients):
    course_id = stub_clients["coursera"]._courses[0].id
    payload = _rpc("get_course_detail", {"course_id": course_id, "source": "Coursera"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "result" in body
    assert body["result"]["id"] == course_id


def test_get_course_detail_not_found(test_client):
    payload = _rpc("get_course_detail", {"course_id": "nonexistent-999", "source": "Coursera"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_get_course_detail_invalid_params(test_client):
    payload = _rpc("get_course_detail", {"course_id": ""})  # missing source
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body


def test_get_course_detail_unconfigured_source(test_client):
    payload = _rpc("get_course_detail", {"course_id": "abc123", "source": "YouTube"})
    resp = test_client.post("/", json=payload)
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32002  # UPSTREAM_ERROR


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


def test_course_deduplicates_skills():
    c = Course(
        id="x",
        title="Test Course",
        platform=CourseSource.COURSERA,
        url="https://example.com",
        skills=["Python", "python", "PYTHON", "Docker"],
    )
    assert len(c.skills) == 2
    assert "Python" in c.skills
    assert "Docker" in c.skills


def test_course_model_dump_api_shape():
    c = _make_course()
    api_dict = c.model_dump_api()
    expected_keys = {
        "id", "title", "platform", "instructor", "url", "description",
        "skills", "skill_level", "duration_hours", "rating", "num_ratings",
        "price", "currency", "free", "language", "certificate",
        "thumbnail_url", "published_date", "fetched_at",
    }
    assert expected_keys.issubset(api_dict.keys())


def test_course_description_truncated_in_api_dump():
    c = Course(
        id="x",
        title="Test",
        platform=CourseSource.EDX,
        url="https://example.com",
        description="x" * 2000,
    )
    api_dict = c.model_dump_api()
    assert len(api_dict["description"]) <= 1000
