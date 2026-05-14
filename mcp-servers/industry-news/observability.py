"""Prometheus metrics and OTel tracer for the Industry News MCP server."""
from __future__ import annotations

from opentelemetry import trace
from prometheus_client import Counter, Histogram

_SERVICE = "mcp-industry-news"

NEWS_FETCH_TOTAL = Counter(
    "mcp_industry_news_fetch_total",
    "Total upstream news fetch calls by source and status",
    ["source", "status"],
)

NEWS_FETCH_DURATION = Histogram(
    "mcp_industry_news_fetch_duration_seconds",
    "Upstream fetch latency by source",
    ["source"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

NEWS_ARTICLES_RETURNED = Histogram(
    "mcp_industry_news_articles_returned",
    "Number of articles returned per search query",
    buckets=[0, 1, 5, 10, 20, 30, 50],
)

CACHE_HIT_TOTAL = Counter(
    "mcp_industry_news_cache_hits_total",
    "Total cache hits by tool",
    ["tool"],
)

CACHE_MISS_TOTAL = Counter(
    "mcp_industry_news_cache_misses_total",
    "Total cache misses by tool",
    ["tool"],
)

TOOL_CALL_TOTAL = Counter(
    "mcp_industry_news_tool_call_total",
    "Total tool invocations by method and status",
    ["method", "status"],
)

TOOL_CALL_DURATION = Histogram(
    "mcp_industry_news_tool_call_duration_seconds",
    "End-to-end latency for tool calls",
    ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

AUDIT_LOG_TOTAL = Counter(
    "mcp_industry_news_audit_log_total",
    "Total audit log events emitted by tool",
    ["tool"],
)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_SERVICE)
