"""Prometheus metrics pushed from Celery workers to the Pushgateway.

These four metric names exactly match the Grafana dashboard queries, so
the Agent/LLM section populates without any dashboard changes.

Usage pattern in agent code:

    from agents.core.gateway_metrics import (
        mcp_tool_calls_total,
        record_llm_tokens,
        push_gateway_metrics,
    )

    # After an MCP call:
    mcp_tool_calls_total.labels(server="job_board", tool="search_jobs", outcome="success").inc()

    # After an LLM call (pass the AIMessage returned by ainvoke):
    record_llm_tokens(response, model="claude-haiku-4-5-20251001")

The dispatcher calls push_gateway_metrics() after each agent phase so
data reaches the Pushgateway within seconds of the invocation completing.
Push errors are logged and swallowed — they never affect agent correctness.
"""
from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

from agents.config import agent_settings
from agents.core.logging import get_logger

logger = get_logger(__name__)

# Isolated registry — only push the four metrics the dashboard queries,
# not the hundreds of per-agent detail metrics in observability.py.
_registry = CollectorRegistry()

agent_invocations_total = Counter(
    "agent_invocations_total",
    "Total agent invocations by name and outcome",
    ["agent_name", "outcome"],
    registry=_registry,
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Agent invocation wall-clock time in seconds",
    ["agent_name"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    registry=_registry,
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed by direction and model",
    ["model", "direction"],
    registry=_registry,
)

mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total",
    "Total MCP tool calls by server, tool, and outcome",
    ["server", "tool", "outcome"],
    registry=_registry,
)


def push_gateway_metrics() -> None:
    """Push the four dashboard metrics to the Prometheus Pushgateway (best-effort)."""
    url = agent_settings.prometheus_pushgateway_url
    if not url:
        return
    try:
        push_to_gateway(url, job="career-agents", registry=_registry)
    except Exception as exc:
        logger.warning("metrics.push_gateway_failed", error=str(exc))


def record_llm_tokens(response: Any, model: str) -> None:
    """Extract token counts from a LangChain AIMessage and update llm_tokens_total.

    Reads ``response.usage_metadata`` (present on AIMessage from langchain-anthropic).
    Safe to call with any object — silently does nothing if usage data is absent.
    """
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return
    in_tok = int(usage.get("input_tokens", 0))
    out_tok = int(usage.get("output_tokens", 0))
    if in_tok:
        llm_tokens_total.labels(model=model, direction="input").inc(in_tok)
    if out_tok:
        llm_tokens_total.labels(model=model, direction="output").inc(out_tok)
