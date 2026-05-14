"""Prometheus metrics and OTel tracer for the LinkedIn Profile MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-linkedin-profile"

# ── Profile fetch metrics ─────────────────────────────────────────────────────

PROFILE_FETCH_TOTAL = Counter(
    "mcp_linkedin_profile_fetch_total",
    "Total LinkedIn profile fetch calls by status",
    ["status"],  # success | error | timeout | open_circuit | not_found
)

PROFILE_FETCH_DURATION = Histogram(
    "mcp_linkedin_profile_fetch_duration_seconds",
    "Profile fetch latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Title normalisation metrics ───────────────────────────────────────────────

TITLE_NORMALIZE_TOTAL = Counter(
    "mcp_linkedin_title_normalize_total",
    "Total job title normalisation calls by method",
    ["method"],  # rules | fallback
)

TITLE_NORMALIZE_CONFIDENCE = Histogram(
    "mcp_linkedin_title_normalize_confidence",
    "Confidence score distribution for title normalisation",
    buckets=[0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0],
)

# ── Connection suggestion metrics ─────────────────────────────────────────────

CONNECTION_SUGGEST_TOTAL = Counter(
    "mcp_linkedin_connection_suggest_total",
    "Total connection suggestion calls by status",
    ["status"],
)

CONNECTION_SUGGEST_RESULTS = Histogram(
    "mcp_linkedin_connection_suggest_results",
    "Number of connection suggestions returned per call",
    buckets=[0, 1, 2, 3, 5, 10, 20, 50],
)

# ── Cache metrics ─────────────────────────────────────────────────────────────

CACHE_HIT_TOTAL = Counter(
    "mcp_linkedin_profile_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_linkedin_profile_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

# ── Rate-limit metrics ────────────────────────────────────────────────────────

RATE_LIMIT_HIT_TOTAL = Counter(
    "mcp_linkedin_profile_rate_limit_hit_total",
    "Total requests rejected by rate limiter by tool",
    ["tool"],
)

# ── Tool-call metrics ─────────────────────────────────────────────────────────

TOOL_CALL_TOTAL = Counter(
    "mcp_linkedin_profile_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_linkedin_profile_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

AUDIT_LOG_TOTAL = Counter(
    "mcp_linkedin_profile_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
