"""Shared async HTTP client dependency."""
import httpx
from fastapi import Request


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """FastAPI dependency — yields the shared httpx client from app state."""
    return request.app.state.http_client
