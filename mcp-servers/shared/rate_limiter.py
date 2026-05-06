"""Token-bucket rate limiter for MCP tool servers.

Each MCP server is an internal service; rate limiting guards against
runaway agent loops and upstream API quota exhaustion.

Limits are applied per (user_id, tool) pair using a Redis sliding-window
counter. When Redis is unavailable the limiter fails open (allows the call)
so that a cache outage does not bring down the whole pipeline.

Usage::

    limiter = RateLimiter(redis_url="redis://localhost:6379/0")
    await limiter.connect()

    allowed = await limiter.check("user-123", "search_jobs", limit=10, window_seconds=60)
    if not allowed:
        raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded")
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets."""

    _KEY_PREFIX = "mcp:ratelimit:"

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._client = await aioredis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def check(
        self,
        user_id: str,
        tool: str,
        *,
        limit: int = 60,
        window_seconds: int = 60,
    ) -> bool:
        """Return True if the request is within the rate limit, False if exceeded."""
        if not self._client:
            return True  # fail open

        key = f"{self._KEY_PREFIX}{user_id}:{tool}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()
            count: int = results[2]
            return count <= limit
        except Exception as exc:
            logger.warning(
                "rate_limiter.check_failed",
                extra={"user_id": user_id, "tool": tool, "error": str(exc)},
            )
            return True  # fail open on Redis error

    async def remaining(
        self,
        user_id: str,
        tool: str,
        *,
        limit: int = 60,
        window_seconds: int = 60,
    ) -> int:
        """Return the number of remaining calls within the current window."""
        if not self._client:
            return limit
        key = f"{self._KEY_PREFIX}{user_id}:{tool}"
        now = time.time()
        window_start = now - window_seconds
        try:
            await self._client.zremrangebyscore(key, "-inf", window_start)
            count: int = await self._client.zcard(key)
            return max(0, limit - count)
        except Exception:
            return limit
