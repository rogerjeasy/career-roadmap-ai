"""list_documents — MCP tool handler."""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseStorageClient
from models import DocumentType, ListDocumentsParams
from observability import (
    AUDIT_LOG_TOTAL,
    DOCUMENTS_PER_USER,
    LIST_RESULTS,
    LIST_TOTAL,
    RATE_LIMIT_HIT_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()
_TOOL_NAME = "list_documents"


async def handle_list_documents(
    params: dict[str, Any],
    request: Request,
    storage: BaseStorageClient,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.list_documents") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                list_params = ListDocumentsParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS, "Invalid list_documents parameters", data=exc.errors()
                )

            allowed = await rate_limiter.check(
                list_params.user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                RATE_LIMIT_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for list_documents")

            docs = await storage.list(
                user_id=list_params.user_id,
                document_type=list_params.document_type,
                limit=list_params.limit,
            )

            LIST_TOTAL.labels(status="success").inc()
            LIST_RESULTS.observe(len(docs))
            DOCUMENTS_PER_USER.observe(len(docs))

            result = {
                "documents": [d.model_dump_api() for d in docs],
                "total_count": len(docs),
                "user_id": list_params.user_id,
            }

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            emit_tool_call_audit(
                server_id="document_store", tool=_TOOL_NAME, user_id=list_params.user_id,
                outcome="ok", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                extra={"document_count": len(docs)},
            )
            span.set_attribute("result_count", len(docs))
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            LIST_TOTAL.labels(status="error").inc()
            logger.error("list_documents.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR, "Internal error during document listing"
            ) from exc
