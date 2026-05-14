"""Prometheus metrics and OTel tracer for the Calendar MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-calendar"

# ── Event creation metrics ────────────────────────────────────────────────────

EVENT_CREATE_TOTAL = Counter(
    "mcp_calendar_event_create_total",
    "Total calendar event creation calls by provider and status",
    ["provider", "status"],
)

EVENT_CREATE_DURATION = Histogram(
    "mcp_calendar_event_create_duration_seconds",
    "Event creation latency per provider",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Weekly tasks metrics ──────────────────────────────────────────────────────

WEEKLY_TASKS_TOTAL = Counter(
    "mcp_calendar_weekly_tasks_total",
    "Total create_weekly_tasks calls by provider and status",
    ["provider", "status"],
)

WEEKLY_TASKS_CREATED = Histogram(
    "mcp_calendar_weekly_tasks_created_count",
    "Number of tasks successfully created per batch by provider",
    ["provider"],
    buckets=[0, 1, 2, 3, 5, 7, 10, 14, 21, 28, 50],
)

# ── List upcoming metrics ─────────────────────────────────────────────────────

LIST_FETCH_TOTAL = Counter(
    "mcp_calendar_list_fetch_total",
    "Total list_upcoming calls by provider and status",
    ["provider", "status"],
)

LIST_FETCH_RESULTS = Histogram(
    "mcp_calendar_list_fetch_results_count",
    "Number of events returned per list_upcoming call",
    ["provider"],
    buckets=[0, 1, 2, 3, 5, 10, 20, 30, 50, 100],
)

# ── Cache metrics ─────────────────────────────────────────────────────────────

CACHE_HIT_TOTAL = Counter(
    "mcp_calendar_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_calendar_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

# ── Rate-limit metrics ────────────────────────────────────────────────────────

RATE_LIMIT_HIT_TOTAL = Counter(
    "mcp_calendar_rate_limit_hit_total",
    "Total requests rejected by rate limiter by tool",
    ["tool"],
)

# ── Tool-call metrics (per JSON-RPC method) ───────────────────────────────────

TOOL_CALL_TOTAL = Counter(
    "mcp_calendar_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_calendar_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Audit metrics ─────────────────────────────────────────────────────────────

AUDIT_LOG_TOTAL = Counter(
    "mcp_calendar_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
