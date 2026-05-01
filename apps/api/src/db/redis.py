"""Async Redis client dependency."""
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Request


async def get_redis(request: Request) -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency — yields the shared Redis client from app state."""
    yield request.app.state.redis
