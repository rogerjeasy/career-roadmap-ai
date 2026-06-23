"""Unit tests for ResponseCache key derivation and no-client fallbacks."""
from __future__ import annotations

import pytest

from shared.cache import ResponseCache

pytestmark = pytest.mark.unit


def test_make_key_is_deterministic_and_param_order_independent() -> None:
    cache = ResponseCache("redis://x")
    k1 = cache._make_key("search_jobs", {"role": "PM", "location": "NYC"})
    k2 = cache._make_key("search_jobs", {"location": "NYC", "role": "PM"})
    assert k1 == k2  # sort_keys makes ordering irrelevant
    assert k1.startswith("mcp:cache:search_jobs:")


def test_make_key_differs_by_tool_and_params() -> None:
    cache = ResponseCache("redis://x")
    base = cache._make_key("search_jobs", {"role": "PM"})
    assert base != cache._make_key("search_jobs", {"role": "SWE"})
    assert base != cache._make_key("other_tool", {"role": "PM"})


async def test_get_returns_none_without_a_connected_client() -> None:
    cache = ResponseCache("redis://x")
    assert await cache.get("t", {"a": 1}) is None


async def test_set_is_a_noop_without_a_client() -> None:
    cache = ResponseCache("redis://x")
    # Must not raise even though there is no Redis connection.
    await cache.set("t", {"a": 1}, {"v": 1})


async def test_get_or_fetch_without_client_calls_fetcher_directly() -> None:
    cache = ResponseCache("redis://x")
    calls = 0

    async def fetcher() -> dict:
        nonlocal calls
        calls += 1
        return {"v": 42}

    result = await cache.get_or_fetch("t", {"a": 1}, fetcher)
    assert result == {"v": 42}
    assert calls == 1


async def test_ping_false_without_client() -> None:
    cache = ResponseCache("redis://x")
    assert await cache.ping() is False
