"""upload_document — MCP tool handler."""
from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.base_client import BaseStorageClient
from models import UploadDocumentParams
from observability import (
    AUDIT_LOG_TOTAL,
    RATE_LIMIT_HIT_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    UPLOAD_DURATION,
    UPLOAD_SIZE_BYTES,
    UPLOAD_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.error_handler import JsonRpcError, JsonRpcErrorCode
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)
_tracer = get_tracer()
_TOOL_NAME = "upload_document"

_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB default; overridden from config


async def handle_upload_document(
    params: dict[str, Any],
    request: Request,
    storage: BaseStorageClient,
    rate_limiter: RateLimiter,
    *,
    rate_limit: int = 30,
    max_file_size_bytes: int = _MAX_FILE_SIZE_BYTES,
    max_documents_per_user: int = 20,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.upload_document") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                up_params = UploadDocumentParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid upload_document parameters",
                    data=exc.errors(),
                )

            # Use the authenticated user_id from the JWT header when available
            effective_user_id = up_params.user_id

            allowed = await rate_limiter.check(
                effective_user_id, _TOOL_NAME, limit=rate_limit, window_seconds=60
            )
            if not allowed:
                RATE_LIMIT_HIT_TOTAL.labels(tool=_TOOL_NAME).inc()
                raise JsonRpcError(JsonRpcErrorCode.RATE_LIMITED, "Rate limit exceeded for upload_document")

            # Decode and validate content
            try:
                content = base64.b64decode(up_params.content_base64)
            except Exception:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "content_base64 is not valid base64",
                )

            if len(content) > max_file_size_bytes:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    f"File too large: {len(content)} bytes exceeds {max_file_size_bytes} bytes limit",
                )

            # Enforce per-user document limit
            existing = await storage.list(user_id=effective_user_id, limit=max_documents_per_user + 1)
            if len(existing) >= max_documents_per_user:
                raise JsonRpcError(
                    JsonRpcErrorCode.UPSTREAM_ERROR,
                    f"Document limit reached: maximum {max_documents_per_user} documents per user",
                )

            document_id = str(uuid.uuid4())
            span.set_attribute("document_id", document_id)
            span.set_attribute("document_type", up_params.document_type.value)
            span.set_attribute("size_bytes", len(content))

            t_store = time.monotonic()
            doc = await storage.upload(
                user_id=effective_user_id,
                document_id=document_id,
                filename=up_params.filename,
                document_type=up_params.document_type,
                content_type=up_params.content_type,
                content=content,
                metadata=up_params.metadata,
            )
            store_latency = time.monotonic() - t_store

            UPLOAD_TOTAL.labels(
                document_type=up_params.document_type.value,
                provider=storage.provider,
                status="success",
            ).inc()
            UPLOAD_SIZE_BYTES.labels(document_type=up_params.document_type.value).observe(len(content))
            UPLOAD_DURATION.labels(provider=storage.provider).observe(store_latency)

            result = {"document": doc.model_dump_api(), "uploaded": True}

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            emit_tool_call_audit(
                server_id="document_store", tool=_TOOL_NAME, user_id=effective_user_id,
                outcome="ok", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                extra={"document_id": document_id, "document_type": up_params.document_type.value, "size_bytes": len(content)},
            )
            logger.info(
                "upload_document.completed",
                user_id=effective_user_id,
                document_id=document_id,
                filename=up_params.filename,
                size_bytes=len(content),
                correlation_id=correlation_id,
            )
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            UPLOAD_TOTAL.labels(
                document_type=params.get("document_type", "unknown"),
                provider=storage.provider,
                status="error",
            ).inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("upload_document.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR, "Internal error during document upload"
            ) from exc
