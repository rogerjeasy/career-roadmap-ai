"""get_job_detail — MCP tool handler.

Fetches the full detail of a specific job posting by ID and source.
Results are cached aggressively (1 hour) since job details rarely change.

JSON-RPC method: ``get_job_detail``
Params: ``GetJobDetailParams``
Result: A ``JobPosting`` dict as returned by ``model_dump_api()``
"""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseJobBoardClient
from models import GetJobDetailParams, JobSource
from observability import (
    AUDIT_LOG_TOTAL,
    CACHE_HIT_TOTAL,
    CACHE_MISS_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

_TOOL_NAME = "get_job_detail"
_CACHE_TTL = 3600  # job details are stable; cache for 1 hour


async def handle_get_job_detail(
    params: dict[str, Any],
    request: Request,
    clients: dict[str, BaseJobBoardClient],
    cache: ResponseCache,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 120,
) -> dict[str, Any]:
    """Top-level handler for the ``get_job_detail`` JSON-RPC method."""
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.get_job_detail") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            # ── Input validation ──────────────────────────────────────────
            try:
                detail_params = GetJobDetailParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid get_job_detail parameters",
                    data=exc.errors(),
                )

            span.set_attribute("job_id", detail_params.job_id)
            span.set_attribute("source", detail_params.source.value)

            # ── Rate limiting ─────────────────────────────────────────────
            allowed = await rate_limiter.check(
                user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                raise JsonRpcError(
                    JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for get_job_detail"
                )

            # ── Cache lookup ──────────────────────────────────────────────
            cache_key_params = {"job_id": detail_params.job_id, "source": detail_params.source, "country": detail_params.country}
            cached = await cache.get(_TOOL_NAME, cache_key_params)
            if cached:
                CACHE_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="cache_hit").inc()
                return cached

            CACHE_MISS_TOTAL.labels(tool=_TOOL_NAME).inc()

            # ── Find the right client ─────────────────────────────────────
            client = _find_client(detail_params.source, clients)
            if client is None:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Source '{detail_params.source}' is not configured",
                )

            # ── Fetch detail ──────────────────────────────────────────────
            posting = await client.get_detail(
                detail_params.job_id,
                country=detail_params.country,
                correlation_id=correlation_id,
            )
            if posting is None:
                raise JsonRpcError(
                    JsonRpcErrorCode.METHOD_NOT_FOUND,
                    f"Job '{detail_params.job_id}' not found on {detail_params.source}",
                )

            result = posting.model_dump_api()

            # ── Cache and audit ───────────────────────────────────────────
            await cache.set(_TOOL_NAME, cache_key_params, result, ttl=_CACHE_TTL)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            emit_tool_call_audit(
                server_id="job_board",
                tool=_TOOL_NAME,
                user_id=user_id,
                outcome="ok",
                latency_ms=int(latency * 1000),
                correlation_id=correlation_id,
            )

            logger.info(
                "get_job_detail.completed",
                job_id=detail_params.job_id,
                source=detail_params.source.value,
                user_id=user_id,
                correlation_id=correlation_id,
                latency_ms=int(latency * 1000),
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error(
                "get_job_detail.unhandled_error",
                error=str(exc),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR,
                "Internal error fetching job detail",
            ) from exc


def _find_client(
    source: JobSource,
    clients: dict[str, BaseJobBoardClient],
) -> BaseJobBoardClient | None:
    for client in clients.values():
        if client.source == source:
            return client
    return None
