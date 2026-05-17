"""Prometheus metrics — exposes /metrics for scraping.

Includes default RED metrics from instrumentator + custom AI counters.
"""
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# ── Custom AI metrics ──────────────────────────────────────
agent_invocations_total = Counter(
    "agent_invocations_total",
    "Total number of agent invocations by name and outcome",
    ["agent_name", "outcome"],  # outcome: success | error | clarification_needed
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed by direction and model",
    ["model", "direction"],  # direction: input | output
)

mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total",
    "Total MCP tool calls by server and tool",
    ["server", "tool", "outcome"],
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Duration of agent invocations in seconds",
    ["agent_name"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# ── Session Manager metrics ────────────────────────────────
session_operations_total = Counter(
    "session_operations_total",
    "Session lifecycle operations by type and outcome",
    ["operation", "outcome"],
    # operation: create | get | get_or_create | delete
    # outcome:   success | not_found | resumed | error
)

# ── SSE stream metrics ─────────────────────────────────────
sse_active_connections = Gauge(
    "sse_active_connections",
    "Number of currently active SSE connections",
)

sse_subscription_duration_seconds = Histogram(
    "sse_subscription_duration_seconds",
    "Duration of SSE connections from subscribe to close",
    ["outcome"],  # completed | client_disconnected | error
    buckets=(5.0, 15.0, 30.0, 60.0, 120.0, 180.0, 300.0),
)

sse_events_forwarded_total = Counter(
    "sse_events_forwarded_total",
    "SSE events forwarded to clients by event type",
    ["event_type"],
)

sse_events_dropped_total = Counter(
    "sse_events_dropped_total",
    "SSE events dropped due to slow consumer backpressure",
    ["event_type"],
)

# ── Middleware metrics ─────────────────────────────────────
case_conversion_errors_total = Counter(
    "case_conversion_errors_total",
    "JSON key case conversion failures in CaseConversionMiddleware",
    ["direction"],  # request | response
)


def setup_prometheus(app: FastAPI) -> None:
    """Mount /metrics endpoint and instrument the FastAPI app."""
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/livez", "/readyz"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)