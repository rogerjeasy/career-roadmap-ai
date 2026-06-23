"""Shared fixtures for the centralised ``mcp-servers/tests`` suite.

Adds the ``mcp-servers/`` root to ``sys.path`` so tests can ``import shared.…``
exactly as the servers do at runtime, and provides an in-memory fake Redis so
the cache can be exercised without a live broker.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class FakeRedis:
    """Minimal async Redis stand-in covering the surface ResponseCache uses.

    Supports the SET-NX-PX lock primitive and TTL-less storage (TTL semantics
    are not exercised by the unit/integration tests).
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: dict[str, int] = {"get": 0, "set": 0, "delete": 0}

    async def get(self, key: str) -> str | None:
        self.calls["get"] += 1
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        px: int | None = None,
    ) -> Any:
        self.calls["set"] += 1
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.calls["delete"] += 1
        self.store.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
