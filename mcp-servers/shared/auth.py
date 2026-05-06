"""API-key authentication for MCP servers.

MCP servers are internal services — they sit behind the agent runtime, not
directly on the public internet. Authentication uses a shared API key passed
in the ``X-MCP-API-Key`` header. The key is validated against the value from
the ``MCP_API_KEY`` environment variable.

Usage in a FastAPI server::

    from shared.auth import verify_api_key

    @app.post("/")
    async def rpc_endpoint(request: Request, _=Depends(verify_api_key)):
        ...
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


class ApiKeyAuth:
    """Callable FastAPI dependency that validates the MCP API key."""

    def __init__(self, api_key: str) -> None:
        self._key = api_key.encode()

    def __call__(self, x_mcp_api_key: str = Header(alias="X-MCP-API-Key")) -> None:
        if not hmac.compare_digest(self._key, x_mcp_api_key.encode()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing MCP API key",
            )


def verify_api_key(x_mcp_api_key: str = Header(alias="X-MCP-API-Key", default="")) -> None:
    """FastAPI dependency — validates X-MCP-API-Key against MCP_API_KEY env var.

    If ``MCP_API_KEY`` is not set, authentication is bypassed (development only).
    """
    expected = os.getenv("MCP_API_KEY", "")
    if not expected:
        return
    if not hmac.compare_digest(expected.encode(), x_mcp_api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing MCP API key",
        )
