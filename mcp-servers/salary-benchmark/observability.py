"""Prometheus metrics and OTel tracer for the Salary Benchmark MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-salary-benchmark"

SALARY_FETCH_TOTAL = Counter(
    "mcp_salary_benchmark_fetch_total",
    "Total upstream salary fetch calls by source and status",
    ["source", "status"],
)

SALARY_FETCH_DURATION = Histogram(
    "mcp_salary_benchmark_fetch_duration_seconds",
    "Upstream fetch latency per source",
    ["source"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

SALARY_SAMPLE_COUNT = Histogram(
    "mcp_salary_benchmark_sample_count",
    "Number of salary data points returned per query",
    buckets=[0, 1, 5, 10, 25, 50, 100, 250],
)

CACHE_HIT_TOTAL = Counter(
    "mcp_salary_benchmark_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_salary_benchmark_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

TOOL_CALL_TOTAL = Counter(
    "mcp_salary_benchmark_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_salary_benchmark_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

AUDIT_LOG_TOTAL = Counter(
    "mcp_salary_benchmark_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
