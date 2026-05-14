"""Test configuration for social-signals MCP server.

Adds both mcp-servers/ (for `shared`) and mcp-servers/social-signals/
(for `clients`, `tools`, `models`, etc.) to sys.path so imports work
the same as in production.
"""
import os
import sys

import pytest

# mcp-servers/social-signals/
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# mcp-servers/
_MCP_DIR = os.path.dirname(_SERVER_DIR)

for path in (_MCP_DIR, _SERVER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture()
def mock_clients():
    """Minimal client stubs that return empty signal lists."""
    from models import SocialSource

    def _make(source: SocialSource):
        client = MagicMock()
        client.source = source
        client.search = AsyncMock(return_value=[])
        return client

    return {
        "hackernews": _make(SocialSource.HACKERNEWS),
        "reddit": _make(SocialSource.REDDIT),
        "devto": _make(SocialSource.DEVTO),
    }


@pytest.fixture()
def mock_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture()
def mock_rate_limiter():
    rl = MagicMock()
    rl.check = AsyncMock(return_value=True)
    return rl


@pytest.fixture()
def test_client(mock_clients, mock_cache, mock_rate_limiter):
    """FastAPI TestClient with mocked dependencies injected at module level."""
    import server

    server._clients = mock_clients
    server._cache = mock_cache
    server._rate_limiter = mock_rate_limiter

    # Bypass lifespan (we injected state directly)
    from fastapi.testclient import TestClient as _TC

    with _TC(server.app) as client:
        yield client
