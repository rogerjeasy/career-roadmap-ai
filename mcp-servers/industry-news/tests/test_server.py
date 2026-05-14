"""Industry News MCP server tests."""
from __future__ import annotations

import json
import sys
import os

import pytest
from fastapi.testclient import TestClient

_this_dir = os.path.dirname(os.path.abspath(__file__))
_server_dir = os.path.dirname(_this_dir)
_mcp_root = os.path.dirname(_server_dir)
for p in (_mcp_root, _server_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from server import app

client = TestClient(app)

_RPC_HEADERS = {"Content-Type": "application/json"}


def _rpc(method: str, params: dict) -> dict:
    resp = client.post(
        "/",
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}),
        headers=_RPC_HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()


def test_livez():
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz():
    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server_id"] == "industry_news"
    assert "RSS" in data["sources"]


def test_unknown_method_returns_error():
    rpc_resp = _rpc("not_a_method", {})
    assert "error" in rpc_resp
    assert rpc_resp["error"]["code"] == -32601


def test_search_news_invalid_params():
    rpc_resp = _rpc("search_news", {"query": ""})
    assert "error" in rpc_resp
    assert rpc_resp["error"]["code"] == -32602


def test_search_news_valid_params():
    rpc_resp = _rpc("search_news", {"query": "machine learning", "limit": 5})
    assert "jsonrpc" in rpc_resp


def test_get_weekly_digest_valid_params():
    rpc_resp = _rpc("get_weekly_digest", {"topics": ["machine learning", "python"], "industry": "technology"})
    assert "jsonrpc" in rpc_resp


def test_parse_error():
    resp = client.post("/", content="not json", headers=_RPC_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32700
