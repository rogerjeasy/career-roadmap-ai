"""normalize_job_title — MCP tool handler."""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError

from clients.title_normalizer import normalize_title
from models import NormalizeJobTitleParams
from observability import (
    AUDIT_LOG_TOTAL,
    TITLE_NORMALIZE_CONFIDENCE,
    TITLE_NORMALIZE_TOTAL,
    TOOL_CALL_DURATION,
    TOOL_CALL_TOTAL,
    get_tracer,
)
from shared.audit import emit_tool_call_audit
from shared.error_handler import JsonRpcError, JsonRpcErrorCode

logger = structlog.get_logger(__name__)
_tracer = get_tracer()
_TOOL_NAME = "normalize_job_title"


async def handle_normalize_job_title(
    params: dict[str, Any],
    request: Request,
    **_: Any,
) -> dict[str, Any]:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    user_id = request.headers.get("X-User-ID", "anonymous")

    with _tracer.start_as_current_span("tool.normalize_job_title") as span:
        span.set_attribute("user_id", user_id)
        span.set_attribute("correlation_id", correlation_id)

        t0 = time.monotonic()
        try:
            try:
                norm_params = NormalizeJobTitleParams(**params)
            except ValidationError as exc:
                raise JsonRpcError(
                    JsonRpcErrorCode.INVALID_PARAMS,
                    "Invalid normalize_job_title parameters",
                    data=exc.errors(),
                )

            span.set_attribute("raw_title", norm_params.raw_title)

            # Always in-process — no network call needed
            result_obj = normalize_title(norm_params.raw_title, norm_params.industry)

            TITLE_NORMALIZE_TOTAL.labels(method="rules").inc()
            TITLE_NORMALIZE_CONFIDENCE.observe(result_obj.confidence)

            result = result_obj.model_dump()

            latency = time.monotonic() - t0
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="ok").inc()
            TOOL_CALL_DURATION.labels(method=_TOOL_NAME).observe(latency)
            AUDIT_LOG_TOTAL.labels(tool=_TOOL_NAME).inc()
            emit_tool_call_audit(
                server_id="linkedin_profile", tool=_TOOL_NAME, user_id=user_id,
                outcome="ok", latency_ms=int(latency * 1000), correlation_id=correlation_id,
                extra={"raw_title": norm_params.raw_title, "canonical": result_obj.canonical_title},
            )
            span.set_attribute("canonical_title", result_obj.canonical_title)
            span.set_attribute("confidence", result_obj.confidence)
            return result

        except JsonRpcError:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="rpc_error").inc()
            raise
        except Exception as exc:
            TOOL_CALL_TOTAL.labels(method=_TOOL_NAME, status="error").inc()
            logger.error("normalize_job_title.unhandled_error", error=str(exc), exc_info=True)
            raise JsonRpcError(
                JsonRpcErrorCode.INTERNAL_ERROR, "Internal error during title normalisation"
            ) from exc
