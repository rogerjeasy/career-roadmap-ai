"""Prometheus metrics and OTel tracer for the Document Store MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-document-store"

# ── Upload metrics ─────────────────────────────────────────────────────────────

UPLOAD_TOTAL = Counter(
    "mcp_document_store_upload_total",
    "Total document uploads by type and status",
    ["document_type", "provider", "status"],
)

UPLOAD_SIZE_BYTES = Histogram(
    "mcp_document_store_upload_size_bytes",
    "Size of uploaded documents in bytes",
    ["document_type"],
    buckets=[
        1024, 10 * 1024, 50 * 1024, 100 * 1024, 500 * 1024,
        1024 * 1024, 5 * 1024 * 1024, 10 * 1024 * 1024,
    ],
)

UPLOAD_DURATION = Histogram(
    "mcp_document_store_upload_duration_seconds",
    "Upload latency to storage provider",
    ["provider"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Download / get metrics ────────────────────────────────────────────────────

GET_TOTAL = Counter(
    "mcp_document_store_get_total",
    "Total get_document calls by status",
    ["status"],
)

# ── List metrics ──────────────────────────────────────────────────────────────

LIST_TOTAL = Counter(
    "mcp_document_store_list_total",
    "Total list_documents calls by status",
    ["status"],
)

LIST_RESULTS = Histogram(
    "mcp_document_store_list_results_count",
    "Number of documents returned per list call",
    buckets=[0, 1, 2, 3, 5, 10, 15, 20, 50],
)

# ── Delete metrics ────────────────────────────────────────────────────────────

DELETE_TOTAL = Counter(
    "mcp_document_store_delete_total",
    "Total delete_document calls by status",
    ["status"],
)

# ── Documents per user ────────────────────────────────────────────────────────

DOCUMENTS_PER_USER = Histogram(
    "mcp_document_store_documents_per_user",
    "Total documents stored per user at list time",
    buckets=[0, 1, 2, 3, 5, 10, 15, 20, 50],
)

# ── Tool call metrics ─────────────────────────────────────────────────────────

TOOL_CALL_TOTAL = Counter(
    "mcp_document_store_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_document_store_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

AUDIT_LOG_TOTAL = Counter(
    "mcp_document_store_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)

RATE_LIMIT_HIT_TOTAL = Counter(
    "mcp_document_store_rate_limit_hit_total",
    "Total requests rejected by rate limiter by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
