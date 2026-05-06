"""Redis-backed response cache for MCP tool servers.

Caches serialised JSON results keyed by a hash of (tool, params).
TTL is configurable per call-site. Cache misses are transparent —
the caller receives ``None`` and is responsible for computing the value.

Usage::

    cache = ResponseCache(redis_url="redis://localhost:6379/0", default_ttl=300)
    await cache.connect()

    result = await cache.get("search_jobs", params)
    if result is None:
        result = await expensive_fetch(params)
        await cache.set("search_jobs", params, result, ttl=600)
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ResponseCache:
    """Async Redis response cache. Requires ``redis[hiredis]`` package."""

    _KEY_PREFIX = "mcp:cache:"

    def __init__(self, redis_url: str, default_ttl: int = 300) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl
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

    def _make_key(self, tool: str, params: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool, "params": params}, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{self._KEY_PREFIX}{tool}:{digest}"

    async def get(self, tool: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self._client:
            return None
        try:
            raw = await self._client.get(self._make_key(tool, params))
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("cache.get_failed", extra={"tool": tool, "error": str(exc)})
        return None

    async def set(
        self,
        tool: str,
        params: dict[str, Any],
        value: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        if not self._client:
            return
        try:
            await self._client.set(
                self._make_key(tool, params),
                json.dumps(value),
                ex=ttl or self._default_ttl,
            )
        except Exception as exc:
            logger.warning("cache.set_failed", extra={"tool": tool, "error": str(exc)})

    async def invalidate(self, tool: str, params: dict[str, Any]) -> None:
        if not self._client:
            return
        try:
            await self._client.delete(self._make_key(tool, params))
        except Exception as exc:
            logger.warning("cache.invalidate_failed", extra={"tool": tool, "error": str(exc)})
