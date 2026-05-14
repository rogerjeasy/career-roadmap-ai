"""Prometheus metrics and OTel tracer for the GitHub Trends MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-github-trends"

GITHUB_FETCH_TOTAL = Counter(
    "mcp_github_trends_fetch_total",
    "Total GitHub API fetch calls by endpoint and status",
    ["endpoint", "status"],
)

GITHUB_FETCH_DURATION = Histogram(
    "mcp_github_trends_fetch_duration_seconds",
    "GitHub API fetch latency by endpoint",
    ["endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

CACHE_HIT_TOTAL = Counter(
    "mcp_github_trends_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_github_trends_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

TOOL_CALL_TOTAL = Counter(
    "mcp_github_trends_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_github_trends_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

AUDIT_LOG_TOTAL = Counter(
    "mcp_github_trends_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)

RATE_LIMIT_REMAINING = Counter(
    "mcp_github_trends_api_rate_limit_remaining_total",
    "GitHub API rate limit remaining (sampled from response headers)",
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
