"""Prometheus metrics — exposes /metrics for scraping.

Includes default RED metrics from instrumentator + custom AI counters.
"""
from fastapi import FastAPI
from prometheus_client import Counter, Histogram
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


def setup_prometheus(app: FastAPI) -> None:
    """Mount /metrics endpoint and instrument the FastAPI app."""
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/livez", "/readyz"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)