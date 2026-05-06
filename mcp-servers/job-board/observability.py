"""Prometheus metrics and OTel tracer for the Job Board MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-job-board"

# ── Per-source fetch metrics ──────────────────────────────────────────────────

JOB_FETCH_TOTAL = Counter(
    "mcp_job_board_fetch_total",
    "Total job-board upstream fetch calls by source and status",
    ["source", "status"],  # status: success | error | timeout | rate_limited
)

JOB_FETCH_DURATION = Histogram(
    "mcp_job_board_fetch_duration_seconds",
    "Upstream fetch latency per source",
    ["source"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

JOB_FETCH_RESULTS = Histogram(
    "mcp_job_board_fetch_results_count",
    "Number of job postings returned per source fetch",
    ["source"],
    buckets=[0, 1, 2, 3, 5, 10, 20, 30, 50],
)

# ── Cache metrics ─────────────────────────────────────────────────────────────

CACHE_HIT_TOTAL = Counter(
    "mcp_job_board_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_job_board_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

# ── Rate-limit metrics ────────────────────────────────────────────────────────

RATE_LIMIT_HIT_TOTAL = Counter(
    "mcp_job_board_rate_limit_hit_total",
    "Total requests rejected by rate limiter by tool",
    ["tool"],
)

# ── Tool-call metrics (per JSON-RPC method) ───────────────────────────────────

TOOL_CALL_TOTAL = Counter(
    "mcp_job_board_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_job_board_tool_call_duration_seconds",
    "End-to-end latency for tool calls (including cache + fetch)",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Data quality metrics ──────────────────────────────────────────────────────

POSTINGS_WITH_SALARY = Counter(
    "mcp_job_board_postings_with_salary_total",
    "Total postings that included salary data by source",
    ["source"],
)

POSTINGS_SKILLS_COUNT = Histogram(
    "mcp_job_board_postings_skills_count",
    "Number of required_skills per posting",
    buckets=[0, 1, 2, 3, 5, 8, 12, 20],
)

# ── Audit log metrics ─────────────────────────────────────────────────────────

AUDIT_LOG_TOTAL = Counter(
    "mcp_job_board_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
