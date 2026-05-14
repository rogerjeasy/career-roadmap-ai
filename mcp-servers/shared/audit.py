"""Structured audit log emitter for MCP tool calls.

CLAUDE.md mandates: every MCP server call must emit a structured log event
with a fixed schema so the audit trail is queryable by log aggregators.

Every tool handler should call ``emit()`` exactly once per invocation —
on completion (success, error, cache-hit, or rate-limited).

Fixed audit event schema
------------------------
event          : "mcp.tool_call"                    (constant)
server_id      : str  e.g. "job_board"
tool           : str  e.g. "search_jobs"
user_id        : str  (from X-User-ID request header; "anonymous" if absent)
outcome        : Literal["ok","cache_hit","rpc_error","error","rate_limited","open_circuit"]
latency_ms     : int
correlation_id : str  (from X-Correlation-ID request header)
timestamp      : ISO-8601 UTC string

Usage::

    from shared.audit import emit_tool_call_audit

    emit_tool_call_audit(
        server_id="job_board",
        tool="search_jobs",
        user_id=user_id,
        outcome="ok",
        latency_ms=240,
        correlation_id=correlation_id,
    )
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import structlog
from prometheus_client import Counter

logger = structlog.get_logger("mcp.audit")

AuditOutcome = Literal["ok", "cache_hit", "rpc_error", "error", "rate_limited", "open_circuit"]

# Audit counter — gives a queryable rate without log aggregation
AUDIT_EVENTS = Counter(
    "mcp_audit_events_total",
    "Total MCP audit events by server, tool, and outcome",
    ["server_id", "tool", "outcome"],
)


def emit_tool_call_audit(
    *,
    server_id: str,
    tool: str,
    user_id: str,
    outcome: AuditOutcome,
    latency_ms: int,
    correlation_id: str = "",
    extra: dict | None = None,
) -> None:
    """Emit a structured audit log event and increment the audit counter.

    Never raises — audit failures must not interrupt the request path.
    """
    try:
        AUDIT_EVENTS.labels(server_id=server_id, tool=tool, outcome=outcome).inc()
        payload: dict = {
            "event": "mcp.tool_call",
            "server_id": server_id,
            "tool": tool,
            "user_id": user_id,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if extra:
            payload.update(extra)
        logger.info("mcp.tool_call", **payload)
    except Exception:
        pass  # Audit must never fail the caller
