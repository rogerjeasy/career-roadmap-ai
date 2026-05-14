"""Redis-backed response cache for MCP tool servers with stampede protection.

Basic usage (cache-aside)::

    cache = ResponseCache(redis_url="redis://localhost:6379/0", default_ttl=300)
    await cache.connect()

    result = await cache.get("search_jobs", params)
    if result is None:
        result = await expensive_fetch(params)
        await cache.set("search_jobs", params, result, ttl=600)

Single-flight / stampede protection::

    async def fetcher() -> dict:
        return await expensive_upstream_call(params)

    result = await cache.get_or_fetch("search_jobs", params, fetcher, ttl=600)

``get_or_fetch`` uses a short-lived Redis lock so that when many concurrent
requests all miss the same hot cache key, exactly one caller performs the
upstream fetch while the others wait and read the cached result.  This prevents
the thundering-herd problem at scale with millions of users.

Lock timeout and poll interval are configurable but sane defaults are chosen:
  lock_ttl_s   : 8 s — how long the fetching caller holds the lock
  poll_interval: 0.1 s — how often waiters re-check the cache
  poll_timeout : 7 s — maximum time a waiter will wait before falling back
                       to its own fetch (belt-and-suspenders)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_LOCK_KEY_PREFIX = "mcp:lock:"
_LOCK_TTL_S = 8          # seconds the fetching caller holds the lock
_POLL_INTERVAL_S = 0.1   # seconds between cache re-checks by waiters
_POLL_TIMEOUT_S = 7.0    # maximum wait time before a waiter fetches independently


class ResponseCache:
    """Async Redis response cache with single-flight stampede protection.

    Requires ``redis[hiredis]`` package.
    """

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
        # Verify connectivity — raises if Redis is unreachable
        await self._client.ping()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def ping(self) -> bool:
        """Return True if Redis is reachable."""
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False

    # ── Cache get / set / invalidate ─────────────────────────────────────────

    def _make_key(self, tool: str, params: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool, "params": params}, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{self._KEY_PREFIX}{tool}:{digest}"

    def _make_lock_key(self, cache_key: str) -> str:
        return f"{_LOCK_KEY_PREFIX}{cache_key}"

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

    # ── Single-flight stampede protection ────────────────────────────────────

    async def get_or_fetch(
        self,
        tool: str,
        params: dict[str, Any],
        fetcher: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
        *,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """Return cached value or call *fetcher* exactly once for a given key.

        If Redis is unavailable, falls back to calling *fetcher* directly.

        Algorithm:
          1. Check cache — return immediately on hit.
          2. Try to acquire a Redis lock (SETNX with short TTL).
          3. If lock acquired → call *fetcher*, store result, release lock.
          4. If lock not acquired → poll cache until the holder populates it
             or *poll_timeout* elapses; if still nothing, call *fetcher* as
             a belt-and-suspenders fallback.
        """
        # Fast path — cache hit
        cached = await self.get(tool, params)
        if cached is not None:
            return cached

        if not self._client:
            return await fetcher()

        cache_key = self._make_key(tool, params)
        lock_key = self._make_lock_key(cache_key)

        # Try to acquire the lock (NX = only if not exists, PX = TTL in ms)
        acquired = await self._try_acquire_lock(lock_key, _LOCK_TTL_S)

        if acquired:
            # We are the designated fetcher
            try:
                result = await fetcher()
                await self.set(tool, params, result, ttl=ttl)
                return result
            finally:
                await self._release_lock(lock_key)
        else:
            # Another caller is fetching — wait for it to populate the cache
            deadline = time.monotonic() + _POLL_TIMEOUT_S
            while time.monotonic() < deadline:
                await asyncio.sleep(_POLL_INTERVAL_S)
                cached = await self.get(tool, params)
                if cached is not None:
                    return cached

            # Belt-and-suspenders: lock holder may have crashed; fetch independently
            logger.warning(
                "cache.stampede_fallback",
                extra={"tool": tool, "hint": "lock holder did not populate cache in time"},
            )
            result = await fetcher()
            await self.set(tool, params, result, ttl=ttl)
            return result

    async def _try_acquire_lock(self, lock_key: str, ttl_s: float) -> bool:
        try:
            result = await self._client.set(
                lock_key, "1", nx=True, px=int(ttl_s * 1000)
            )
            return result is not None
        except Exception:
            return False  # Fail open — callers proceed independently

    async def _release_lock(self, lock_key: str) -> None:
        try:
            await self._client.delete(lock_key)
        except Exception:
            pass  # Lock TTL will expire naturally
