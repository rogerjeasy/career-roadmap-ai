"""Integration tests for ResponseCache against an in-memory fake Redis.

Covers the cache-aside roundtrip and the single-flight stampede protection that
guards hot keys from a thundering herd of concurrent misses.
"""
from __future__ import annotations

import asyncio

import pytest

from shared.cache import ResponseCache

pytestmark = pytest.mark.integration


@pytest.fixture
def cache(fake_redis) -> ResponseCache:
    c = ResponseCache("redis://fake", default_ttl=300)
    c._client = fake_redis  # bypass connect(); inject the fake
    return c


async def test_set_then_get_roundtrip(cache: ResponseCache) -> None:
    await cache.set("search_jobs", {"role": "PM"}, {"results": [1, 2, 3]})
    assert await cache.get("search_jobs", {"role": "PM"}) == {"results": [1, 2, 3]}


async def test_invalidate_removes_entry(cache: ResponseCache) -> None:
    await cache.set("t", {"a": 1}, {"v": 1})
    await cache.invalidate("t", {"a": 1})
    assert await cache.get("t", {"a": 1}) is None


async def test_get_or_fetch_caches_first_result(cache: ResponseCache) -> None:
    calls = 0

    async def fetcher() -> dict:
        nonlocal calls
        calls += 1
        return {"v": calls}

    first = await cache.get_or_fetch("t", {"a": 1}, fetcher)
    second = await cache.get_or_fetch("t", {"a": 1}, fetcher)
    assert first == {"v": 1}
    assert second == {"v": 1}  # served from cache, not re-fetched
    assert calls == 1


async def test_single_flight_runs_fetcher_once_under_concurrency(cache: ResponseCache) -> None:
    calls = 0

    async def slow_fetcher() -> dict:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)  # simulate an upstream call
        return {"v": "fetched"}

    # 10 concurrent callers all miss the same key simultaneously.
    results = await asyncio.gather(
        *(cache.get_or_fetch("hot", {"k": 1}, slow_fetcher) for _ in range(10))
    )

    assert all(r == {"v": "fetched"} for r in results)
    assert calls == 1  # exactly one upstream fetch despite the herd
