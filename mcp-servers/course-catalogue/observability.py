"""Prometheus metrics and OTel tracer for the Course Catalogue MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-course-catalogue"

# ── Per-source fetch metrics ──────────────────────────────────────────────────

COURSE_FETCH_TOTAL = Counter(
    "mcp_course_catalogue_fetch_total",
    "Total course catalogue upstream fetch calls by source and status",
    ["source", "status"],  # status: success | error | timeout | rate_limited
)

COURSE_FETCH_DURATION = Histogram(
    "mcp_course_catalogue_fetch_duration_seconds",
    "Upstream fetch latency per source",
    ["source"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

COURSE_FETCH_RESULTS = Histogram(
    "mcp_course_catalogue_fetch_results_count",
    "Number of courses returned per source fetch",
    ["source"],
    buckets=[0, 1, 2, 3, 5, 10, 20, 30, 50],
)

# ── Cache metrics ─────────────────────────────────────────────────────────────

CACHE_HIT_TOTAL = Counter(
    "mcp_course_catalogue_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_course_catalogue_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

# ── Rate-limit metrics ────────────────────────────────────────────────────────

RATE_LIMIT_HIT_TOTAL = Counter(
    "mcp_course_catalogue_rate_limit_hit_total",
    "Total requests rejected by rate limiter by tool",
    ["tool"],
)

# ── Tool-call metrics (per JSON-RPC method) ───────────────────────────────────

TOOL_CALL_TOTAL = Counter(
    "mcp_course_catalogue_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_course_catalogue_tool_call_duration_seconds",
    "End-to-end latency for tool calls (including cache + fetch)",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Data quality metrics ──────────────────────────────────────────────────────

COURSES_WITH_RATING = Counter(
    "mcp_course_catalogue_courses_with_rating_total",
    "Total courses that included rating data by source",
    ["source"],
)

COURSES_WITH_DURATION = Counter(
    "mcp_course_catalogue_courses_with_duration_total",
    "Total courses that included duration data by source",
    ["source"],
)

FREE_COURSES_TOTAL = Counter(
    "mcp_course_catalogue_free_courses_total",
    "Total free courses returned by source",
    ["source"],
)

# ── Audit log metrics ─────────────────────────────────────────────────────────

AUDIT_LOG_TOTAL = Counter(
    "mcp_course_catalogue_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
