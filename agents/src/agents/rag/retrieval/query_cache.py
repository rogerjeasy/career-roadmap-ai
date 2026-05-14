"""Redis-backed query cache for RAG retrieval results.

Caches assembled list[dict] (RagChunk-serialised) keyed on a sha256 hash
of the compound retrieval query, sorted namespace list, and top_k.  A cache
hit in ContextAssembler bypasses both the HyDE LLM call and the Pinecone
fan-out, saving 500ms–2s per request for repeated or similar sessions.

Enable with: RAG_CACHE_ENABLED=true in .env
TTL:         RAG_CACHE_TTL_SECONDS (default: 3600 — 1 hour)

Cache key design:
  sha256(query + "|" + ",".join(sorted(namespaces)) + "|" + str(top_k))

The compound query already encodes the user message, target role, current
role, and skills (see ContextAssembler._build_query), so the key is
effectively per-user-intent while allowing users with identical search
contexts to share a cache entry (beneficial for the knowledge layer).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.observability import (
    RAG_CACHE_HIT_TOTAL,
    RAG_CACHE_MISS_TOTAL,
    RAG_CACHE_SET_DURATION,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.query_cache")

_KEY_PREFIX = "rag:query:"


class RagQueryCache:
    """Wraps an async Redis client with RAG-specific serialisation and metrics.

    Stores and retrieves ``list[dict]`` — each dict is a serialised ``RagChunk``
    produced by ``dataclasses.asdict()``.  The caller (``ContextAssembler``) is
    responsible for converting between dicts and dataclasses so this class
    stays free of ``RagChunk`` imports.
    """

    def __init__(self, redis_url: str | None = None, ttl: int | None = None) -> None:
        try:
            import redis.asyncio as aioredis  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "redis package is required. "
                "Add it to pyproject.toml: redis>=5.0"
            ) from exc

        url = redis_url or str(agent_settings.redis_url)
        self._redis = aioredis.from_url(url, decode_responses=True)
        self._ttl = ttl if ttl is not None else agent_settings.rag_cache_ttl_seconds

    # ── Key construction ──────────────────────────────────────────────────────

    @staticmethod
    def make_key(query: str, namespaces: list[str], top_k: int) -> str:
        """Return a deterministic Redis key for the given retrieval parameters."""
        fingerprint = "|".join([
            query,
            ",".join(sorted(namespaces)),
            str(top_k),
        ])
        digest = hashlib.sha256(fingerprint.encode()).hexdigest()
        return f"{_KEY_PREFIX}{digest}"

    # ── Read / write ──────────────────────────────────────────────────────────

    async def get(self, cache_key: str) -> list[dict[str, Any]] | None:
        """Return cached chunk dicts, or None on miss or deserialisation error."""
        with _tracer.start_as_current_span("rag.cache.get") as span:
            span.set_attribute("key_prefix", cache_key[:24])
            try:
                raw = await self._redis.get(cache_key)
                if raw is None:
                    RAG_CACHE_MISS_TOTAL.inc()
                    span.set_attribute("hit", False)
                    return None

                data: list[dict[str, Any]] = json.loads(raw)
                RAG_CACHE_HIT_TOTAL.inc()
                span.set_attribute("hit", True)
                span.set_attribute("chunks", len(data))
                logger.debug(
                    "rag.cache.hit",
                    key_prefix=cache_key[:24],
                    chunks=len(data),
                )
                return data

            except Exception as exc:
                RAG_CACHE_MISS_TOTAL.inc()
                span.set_attribute("hit", False)
                logger.warning("rag.cache.get_error", error=str(exc))
                return None

    async def set(self, cache_key: str, data: list[dict[str, Any]]) -> None:
        """Write chunk dicts to Redis. Errors are swallowed — cache is best-effort."""
        t0 = time.monotonic()
        with _tracer.start_as_current_span("rag.cache.set") as span:
            span.set_attribute("chunks", len(data))
            span.set_attribute("ttl_seconds", self._ttl)
            try:
                await self._redis.setex(cache_key, self._ttl, json.dumps(data))
                RAG_CACHE_SET_DURATION.observe(time.monotonic() - t0)
                logger.debug(
                    "rag.cache.set",
                    key_prefix=cache_key[:24],
                    chunks=len(data),
                    ttl=self._ttl,
                )
            except Exception as exc:
                RAG_CACHE_SET_DURATION.observe(time.monotonic() - t0)
                logger.warning("rag.cache.set_error", error=str(exc))

    async def close(self) -> None:
        """Release the underlying Redis connection pool."""
        await self._redis.aclose()


# ── Module-level singleton ────────────────────────────────────────────────────

_CACHE: RagQueryCache | None = None


def get_rag_cache() -> RagQueryCache:
    """Return the process-level RagQueryCache singleton."""
    global _CACHE
    if _CACHE is None:
        _CACHE = RagQueryCache()
    return _CACHE
