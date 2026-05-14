"""Pytest configuration for LinkedIn Profile MCP server tests."""
import os
import sys

# Add mcp-servers/ and mcp-servers/linkedin-profile/ to sys.path
_LINKEDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MCP_SERVERS_DIR = os.path.dirname(_LINKEDIN_DIR)

for path in (_MCP_SERVERS_DIR, _LINKEDIN_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MCP_REDIS_URL", "redis://localhost:6379/9")


@pytest.fixture
def anyio_backend():
    return "asyncio"
