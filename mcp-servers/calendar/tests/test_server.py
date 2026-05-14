"""Tests for the Calendar MCP server JSON-RPC dispatcher."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": id}


def _post(client, payload: dict) -> dict:
    resp = client.post(
        "/", content=json.dumps(payload), headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200
    return resp.json()


# ── Health endpoints ──────────────────────────────────────────────────────────


def test_livez(test_client):
    resp = test_client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz(test_client):
    resp = test_client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "providers" in data
    assert "google" in data["providers"]
    assert "outlook" in data["providers"]


# ── Parse / validation errors ─────────────────────────────────────────────────


def test_invalid_json(test_client):
    resp = test_client.post("/", content="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32700  # PARSE_ERROR


def test_method_not_found(test_client):
    body = _post(test_client, _rpc("nonexistent_method"))
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_invalid_jsonrpc_version(test_client):
    payload = {"jsonrpc": "1.0", "method": "create_event", "params": {}, "id": 1}
    body = _post(test_client, payload)
    assert "error" in body
    assert body["error"]["code"] == -32600  # INVALID_REQUEST


# ── create_event ──────────────────────────────────────────────────────────────


def test_create_event_google_success(test_client):
    body = _post(
        test_client,
        _rpc(
            "create_event",
            {
                "provider": "google",
                "access_token": "fake_token",
                "title": "Complete React Module",
                "start_datetime": "2026-05-11T09:00:00",
                "end_datetime": "2026-05-11T10:00:00",
                "timezone": "UTC",
                "reminder_minutes": [60, 10],
            },
        ),
    )
    assert "result" in body
    result = body["result"]
    assert result["provider"] == "google"
    assert "event" in result
    assert result["event"]["title"] == "Test Event"


def test_create_event_outlook_success(test_client):
    body = _post(
        test_client,
        _rpc(
            "create_event",
            {
                "provider": "outlook",
                "access_token": "fake_token",
                "title": "Milestone: Week 3 Complete",
                "start_datetime": "2026-05-11T09:00:00",
                "end_datetime": "2026-05-11T09:30:00",
                "timezone": "Europe/Zurich",
            },
        ),
    )
    assert "result" in body
    result = body["result"]
    assert result["provider"] == "outlook"
    assert result["event"]["provider"] == "outlook"


def test_create_event_missing_required_params(test_client):
    body = _post(test_client, _rpc("create_event", {"provider": "google"}))
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


def test_create_event_missing_access_token(test_client):
    body = _post(
        test_client,
        _rpc(
            "create_event",
            {
                "provider": "google",
                "access_token": "",  # empty — fails min_length=1
                "title": "Test",
                "start_datetime": "2026-05-11T09:00:00",
                "end_datetime": "2026-05-11T10:00:00",
            },
        ),
    )
    assert "error" in body


def test_create_event_upstream_error(test_client, mock_google_client):
    import httpx

    mock_google_client.create_event = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=httpx.Request("POST", "https://example.com"),
            response=httpx.Response(401),
        )
    )
    body = _post(
        test_client,
        _rpc(
            "create_event",
            {
                "provider": "google",
                "access_token": "expired_token",
                "title": "Test",
                "start_datetime": "2026-05-11T09:00:00",
                "end_datetime": "2026-05-11T10:00:00",
            },
        ),
    )
    assert "error" in body
    assert body["error"]["code"] == -32002  # UPSTREAM_ERROR


# ── create_weekly_tasks ───────────────────────────────────────────────────────


_WEEKLY_TASKS_PARAMS = {
    "provider": "google",
    "access_token": "fake_token",
    "week_start": "2026-05-11",
    "timezone": "UTC",
    "tasks": [
        {
            "title": "Python fundamentals",
            "day_of_week": 0,
            "start_time": "09:00",
            "duration_minutes": 60,
            "task_type": "learning",
        },
        {
            "title": "Build REST API",
            "day_of_week": 2,
            "start_time": "10:00",
            "duration_minutes": 90,
            "task_type": "practice",
        },
        {
            "title": "Week 1 milestone",
            "day_of_week": 4,
            "start_time": "17:00",
            "duration_minutes": 30,
            "task_type": "milestone",
        },
    ],
}


def test_create_weekly_tasks_google_success(test_client):
    body = _post(test_client, _rpc("create_weekly_tasks", _WEEKLY_TASKS_PARAMS))
    assert "result" in body
    result = body["result"]
    assert result["total_requested"] == 3
    assert result["total_created"] == 1  # mock returns 1 created event
    assert result["total_failed"] == 0
    assert result["week_start"] == "2026-05-11"
    assert result["provider"] == "google"


def test_create_weekly_tasks_with_partial_failure(test_client, mock_google_client):
    from models import CalendarEvent, CalendarProvider

    created_event = CalendarEvent(
        id="g_1",
        title="Python fundamentals",
        description="",
        start=datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),
        provider=CalendarProvider.GOOGLE,
    )
    failed_task = {"title": "Build REST API", "day_of_week": 2, "error": "API quota exceeded"}

    mock_google_client.create_events_batch = AsyncMock(
        return_value=([created_event], [failed_task])
    )

    body = _post(test_client, _rpc("create_weekly_tasks", _WEEKLY_TASKS_PARAMS))
    assert "result" in body
    result = body["result"]
    assert result["total_created"] == 1
    assert result["total_failed"] == 1
    assert result["failed_tasks"][0]["title"] == "Build REST API"


def test_create_weekly_tasks_outlook(test_client):
    params = {**_WEEKLY_TASKS_PARAMS, "provider": "outlook"}
    body = _post(test_client, _rpc("create_weekly_tasks", params))
    assert "result" in body
    result = body["result"]
    assert result["provider"] == "outlook"


def test_create_weekly_tasks_missing_tasks(test_client):
    body = _post(
        test_client,
        _rpc(
            "create_weekly_tasks",
            {
                "provider": "google",
                "access_token": "fake_token",
                "week_start": "2026-05-11",
                "tasks": [],  # empty — fails min_length=1
            },
        ),
    )
    assert "error" in body
    assert body["error"]["code"] == -32602  # INVALID_PARAMS


def test_create_weekly_tasks_invalid_week_start(test_client):
    params = {**_WEEKLY_TASKS_PARAMS, "week_start": "not-a-date"}
    body = _post(test_client, _rpc("create_weekly_tasks", params))
    assert "error" in body


# ── list_upcoming ─────────────────────────────────────────────────────────────


def test_list_upcoming_google_returns_events(test_client):
    body = _post(
        test_client,
        _rpc(
            "list_upcoming",
            {
                "provider": "google",
                "access_token": "fake_token",
                "max_results": 10,
            },
        ),
    )
    assert "result" in body
    result = body["result"]
    assert result["total_count"] == 1
    assert result["provider"] == "google"
    assert result["events"][0]["title"] == "Upcoming Event"


def test_list_upcoming_outlook_returns_events(test_client):
    body = _post(
        test_client,
        _rpc(
            "list_upcoming",
            {
                "provider": "outlook",
                "access_token": "fake_token",
            },
        ),
    )
    assert "result" in body
    result = body["result"]
    assert result["provider"] == "outlook"
    assert result["total_count"] == 1


def test_list_upcoming_cache_hit(test_client, mock_cache):
    cached_result = {
        "events": [],
        "total_count": 0,
        "provider": "google",
        "time_min": None,
        "time_max": None,
        "fetched_at": "2026-05-11T00:00:00+00:00",
    }
    mock_cache.get = AsyncMock(return_value=cached_result)

    body = _post(
        test_client,
        _rpc("list_upcoming", {"provider": "google", "access_token": "fake_token"}),
    )
    assert "result" in body
    assert body["result"]["total_count"] == 0


def test_list_upcoming_missing_access_token(test_client):
    body = _post(
        test_client,
        _rpc("list_upcoming", {"provider": "google", "access_token": ""}),
    )
    assert "error" in body


def test_list_upcoming_unknown_provider(test_client, mock_clients):
    # Remove google client to simulate unconfigured provider
    mock_clients.pop("google", None)

    body = _post(
        test_client,
        _rpc("list_upcoming", {"provider": "google", "access_token": "fake_token"}),
    )
    assert "error" in body
    assert body["error"]["code"] == -32002  # UPSTREAM_ERROR


# ── Rate-limit enforcement ────────────────────────────────────────────────────


def test_rate_limit_exceeded_create_event(test_client, mock_rate_limiter):
    mock_rate_limiter.check = AsyncMock(return_value=False)
    body = _post(
        test_client,
        _rpc(
            "create_event",
            {
                "provider": "google",
                "access_token": "fake_token",
                "title": "Test",
                "start_datetime": "2026-05-11T09:00:00",
                "end_datetime": "2026-05-11T10:00:00",
            },
        ),
    )
    assert "error" in body
    assert body["error"]["code"] == -32000  # RATE_LIMITED


def test_rate_limit_exceeded_list_upcoming(test_client, mock_rate_limiter):
    mock_rate_limiter.check = AsyncMock(return_value=False)
    body = _post(
        test_client,
        _rpc("list_upcoming", {"provider": "google", "access_token": "fake_token"}),
    )
    assert "error" in body
    assert body["error"]["code"] == -32000  # RATE_LIMITED
