"""Tests for the Social Signals MCP server JSON-RPC dispatcher."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": id}


def _post(client, payload: dict) -> dict:
    resp = client.post("/", content=json.dumps(payload), headers={"Content-Type": "application/json"})
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
    assert "sources" in data


# ── Parse / validation errors ─────────────────────────────────────────────────


def test_invalid_json(test_client):
    resp = test_client.post("/", content="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32700  # PARSE_ERROR


def test_method_not_found(test_client):
    body = _post(test_client, _rpc("nonexistent_method"))
    assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


def test_invalid_params_missing_stacks(test_client):
    body = _post(test_client, _rpc("get_hackernews_signals", {}))
    assert "error" in body


# ── get_hackernews_signals ────────────────────────────────────────────────────


def test_get_hackernews_signals_returns_empty_on_no_results(test_client):
    body = _post(test_client, _rpc("get_hackernews_signals", {"stacks": ["Python"]}))
    assert "result" in body
    result = body["result"]
    assert result["total_count"] == 0
    assert result["source"] == "HackerNews"
    assert result["stacks_queried"] == ["Python"]


def test_get_hackernews_signals_returns_signals(test_client, mock_clients):
    from models import SocialSignal, SocialSource

    signal = SocialSignal(
        id="hn_1",
        title="FastAPI is awesome",
        url="https://news.ycombinator.com/item?id=1",
        source=SocialSource.HACKERNEWS,
        score=250,
        comment_count=42,
        author="user123",
        published_at=datetime.now(timezone.utc),
        tech_stack=["Python"],
    )
    mock_clients["hackernews"].search = AsyncMock(return_value=[signal])

    body = _post(test_client, _rpc("get_hackernews_signals", {"stacks": ["Python"], "limit": 5}))
    assert "result" in body
    result = body["result"]
    assert result["total_count"] == 1
    assert result["signals"][0]["title"] == "FastAPI is awesome"
    assert result["signals"][0]["score"] == 250


# ── get_reddit_signals ────────────────────────────────────────────────────────


def test_get_reddit_signals_returns_empty(test_client):
    body = _post(test_client, _rpc("get_reddit_signals", {"stacks": ["React"]}))
    assert "result" in body
    result = body["result"]
    assert result["source"] == "Reddit"
    assert result["total_count"] == 0


def test_get_reddit_signals_with_signals(test_client, mock_clients):
    from models import SocialSignal, SocialSource

    signal = SocialSignal(
        id="reddit_abc",
        title="React v19 released",
        url="https://reddit.com/r/reactjs/comments/abc",
        source=SocialSource.REDDIT,
        score=1200,
        comment_count=88,
        author="dev_poster",
        tech_stack=["React"],
    )
    mock_clients["reddit"].search = AsyncMock(return_value=[signal])

    body = _post(test_client, _rpc("get_reddit_signals", {"stacks": ["React"], "time_filter": "week"}))
    assert "result" in body
    result = body["result"]
    assert result["total_count"] == 1
    assert result["signals"][0]["score"] == 1200


# ── get_twitter_signals ───────────────────────────────────────────────────────


def test_get_twitter_signals_skipped_when_no_client(test_client):
    """Twitter client is absent in fixture — tool should return empty gracefully."""
    body = _post(test_client, _rpc("get_twitter_signals", {"stacks": ["Python"]}))
    assert "result" in body
    result = body["result"]
    assert result["total_count"] == 0
    assert result["source"] == "Twitter/X"


# ── get_devto_signals ─────────────────────────────────────────────────────────


def test_get_devto_signals_returns_empty(test_client):
    body = _post(test_client, _rpc("get_devto_signals", {"stacks": ["TypeScript"]}))
    assert "result" in body
    assert body["result"]["source"] == "Dev.to"


# ── get_trending_topics ───────────────────────────────────────────────────────


def test_get_trending_topics_returns_topics(test_client, mock_clients):
    from models import SocialSignal, SocialSource

    signals = [
        SocialSignal(
            id=f"hn_{i}",
            title=f"Python article {i}",
            url=f"https://example.com/{i}",
            source=SocialSource.HACKERNEWS,
            score=100 + i * 10,
            comment_count=5,
            tech_stack=["Python"],
        )
        for i in range(5)
    ]
    mock_clients["hackernews"].search = AsyncMock(return_value=signals)
    mock_clients["reddit"].search = AsyncMock(return_value=[])
    mock_clients["devto"].search = AsyncMock(return_value=[])

    body = _post(test_client, _rpc("get_trending_topics", {"stacks": ["Python"], "limit": 5}))
    assert "result" in body
    result = body["result"]
    assert result["total_signals_analysed"] == 5
    assert len(result["topics"]) >= 1
    assert result["topics"][0]["stack"] == "Python"


def test_get_trending_topics_no_sources_raises(test_client, mock_clients):
    """Request sources filter that matches no client → upstream error."""
    body = _post(
        test_client,
        _rpc("get_trending_topics", {"stacks": ["Python"], "sources": ["Twitter/X"]}),
    )
    # Twitter not in clients fixture → no active clients → error
    assert "error" in body


# ── Rate-limit enforcement ────────────────────────────────────────────────────


def test_rate_limit_exceeded(test_client, mock_rate_limiter):
    mock_rate_limiter.check = AsyncMock(return_value=False)
    body = _post(test_client, _rpc("get_hackernews_signals", {"stacks": ["Go"]}))
    assert "error" in body
    assert body["error"]["code"] == -32000  # RATE_LIMITED
