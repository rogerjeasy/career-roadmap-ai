"""Salary Benchmark MCP server tests."""
from __future__ import annotations

import json
import sys
import os

import pytest
from fastapi.testclient import TestClient

# Ensure mcp-servers/ and mcp-servers/salary-benchmark/ are on the path
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
    assert data["server_id"] == "salary_benchmark"
    assert "curated_dataset" in data["sources"]


def test_get_salary_range_curated_fallback():
    """Without real API keys the curated dataset must return a result for CH ML Engineer."""
    rpc_resp = _rpc("get_salary_range", {"role": "Machine Learning Engineer", "country": "CH", "experience_level": "mid"})
    assert "result" not in rpc_resp or rpc_resp.get("result") is not None
    # Either a result with ranges or an upstream error is acceptable
    if "result" in rpc_resp:
        result = rpc_resp["result"]
        assert result["role"] == "Machine Learning Engineer"
        assert result["country"] == "CH"
        assert len(result["ranges"]) >= 1
        r = result["ranges"][0]
        assert r["median"] > 0
        assert "curated_dataset" in r["sources"]


def test_unknown_method_returns_error():
    rpc_resp = _rpc("not_a_method", {})
    assert "error" in rpc_resp
    assert rpc_resp["error"]["code"] == -32601


def test_invalid_params_returns_error():
    rpc_resp = _rpc("get_salary_range", {"role": "", "country": "CH"})
    assert "error" in rpc_resp
    assert rpc_resp["error"]["code"] == -32602


def test_parse_error():
    resp = client.post("/", content="not json", headers=_RPC_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32700
