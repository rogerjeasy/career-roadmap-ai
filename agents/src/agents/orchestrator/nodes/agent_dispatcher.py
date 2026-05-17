"""Node 4 + 5 — dispatch_and_collect.

Executes the task DAG built by ``DagBuilderNode``:
- Phase nodes with no dependencies run concurrently via ``asyncio.gather``.
- Phases that depend on earlier results run after their predecessors complete.

Each agent invocation:
  1. Respects the per-agent timeout from ``TaskNode.retry_policy``.
  2. Retries transient failures with exponential back-off up to
     ``retry_policy.max_attempts`` times.
  3. Non-required agents that exhaust all retries produce a PARTIAL result
     so synthesis can proceed without them.
  4. Required agents that exhaust all retries produce a FAILED result.

Running agents in-process with asyncio (rather than via Celery sub-tasks)
keeps latency low for the common case. The ``run_agent`` Celery task is
available for long-running or CPU-bound agents.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.bus.publisher import EventPublisher
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.results import AgentResult, AgentResultStatus
from agents.contracts.tasks import AgentType
from agents.core.agent_registry import registry
from agents.core.context import AgentContext, RagChunk
from agents.core.exceptions import AgentTimeoutError
from agents.core.logging import get_logger
from agents.core.gateway_metrics import (
    agent_duration_seconds,
    agent_invocations_total,
    push_gateway_metrics,
)
from agents.core.observability import (
    AGENT_DISPATCH_DURATION,
    AGENT_RETRY_TOTAL,
    AGENT_SKIP_TOTAL,
    get_tracer,
)
from agents.orchestrator.state import OrchestratorState, TaskNode
from agents.persistence.interfaces import IRoadmapStore
from agents.persistence.noop_store import NoOpRoadmapStore

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.nodes.agent_dispatcher")

# Default retry policy applied when ``TaskNode.retry_policy`` is absent or
# missing individual keys (should not happen in practice).
_DEFAULT_POLICY: dict[str, Any] = {
    "max_attempts": 2,
    "timeout_seconds": 60,
    "backoff_seconds": 2.0,
}


def make_agent_dispatcher(
    event_publisher: EventPublisher,
    store: IRoadmapStore | None = None,
) -> "AgentDispatcherNode":
    return AgentDispatcherNode(event_publisher, store or NoOpRoadmapStore())


class AgentDispatcherNode:
    def __init__(self, event_publisher: EventPublisher, store: IRoadmapStore) -> None:
        self._events = event_publisher
        self._store = store

    async def __call__(self, state: OrchestratorState) -> dict:
        dag: list[TaskNode] = state["task_dag"]
        roadmap_id: str | None = state.get("roadmap_id")
        completed: dict[str, AgentResult] = {}

        phases = _topological_phases(dag)

        for phase_index, phase_nodes in enumerate(phases):
            logger.info(
                "node.dispatcher.phase_start",
                phase=phase_index + 1,
                agents=[n["agent_type"].value for n in phase_nodes],
                session_id=state["session_id"],
            )
            tasks = [
                self._run_agent_with_retry(node, state, completed)
                for node in phase_nodes
            ]
            phase_results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, result in zip(phase_nodes, phase_results):
                agent_key = node["agent_type"].value
                if isinstance(result, Exception):
                    logger.error(
                        "node.dispatcher.unhandled_exception",
                        agent=agent_key,
                        error=str(result),
                    )
                    completed[agent_key] = AgentResult(
                        task_id=node["task_id"],
                        agent_type=agent_key,
                        status=AgentResultStatus.FAILED,
                        error_message=str(result),
                    )
                else:
                    completed[agent_key] = result  # type: ignore[assignment]
                    # Persist this agent's output incrementally as soon as it completes.
                    if (
                        roadmap_id
                        and not isinstance(result, Exception)
                        and result.status == AgentResultStatus.COMPLETED
                        and result.output
                    ):
                        try:
                            await self._store.persist_agent_output(
                                roadmap_id, agent_key, result.output
                            )
                        except Exception as exc:
                            logger.warning(
                                "node.dispatcher.persist_failed",
                                agent=agent_key,
                                roadmap_id=roadmap_id,
                                error=str(exc),
                            )

            # Push dashboard metrics to Pushgateway after each phase (best-effort).
            asyncio.get_running_loop().run_in_executor(None, push_gateway_metrics)

        return {"agent_results": completed}

    # ── Per-agent retry + timeout ─────────────────────────────────────────

    async def _run_agent_with_retry(
        self,
        node: TaskNode,
        state: OrchestratorState,
        prior_results: dict[str, AgentResult],
    ) -> AgentResult:
        agent_type: AgentType = node["agent_type"]
        agent_key = agent_type.value
        policy = {**_DEFAULT_POLICY, **node.get("retry_policy", {})}
        max_attempts: int = int(policy["max_attempts"])
        timeout_sec: float = float(policy["timeout_seconds"])
        backoff_sec: float = float(policy["backoff_seconds"])
        is_required: bool = bool(node.get("is_required", True))
        t_start = time.monotonic()

        self._emit(AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            session_id=state["session_id"],
            user_id=state["user_id"],
            correlation_id=state["request_id"],
            payload={"agent": agent_key, "max_attempts": max_attempts},
        ))

        last_error: str = ""
        result: AgentResult | None = None

        for attempt in range(1, max_attempts + 1):
            with _tracer.start_as_current_span("agent.dispatch") as span:
                span.set_attribute("agent_type", agent_key)
                span.set_attribute("attempt", attempt)
                span.set_attribute("timeout_seconds", timeout_sec)
                t0 = time.monotonic()

                try:
                    if not registry.is_available(agent_type):
                        result = _stub_result(node, "Agent not yet registered.")
                        span.set_attribute("stub", True)
                        span.set_status(Status(StatusCode.OK))
                        break

                    context = _build_context(node, state, prior_results)
                    agent = registry.get(agent_type)

                    result = await asyncio.wait_for(
                        agent.run(context), timeout=timeout_sec
                    )

                    elapsed = time.monotonic() - t0
                    AGENT_DISPATCH_DURATION.labels(
                        agent_type=agent_key,
                        status=result.status.value,
                    ).observe(elapsed)
                    span.set_attribute("duration_ms", int(elapsed * 1000))
                    span.set_status(Status(StatusCode.OK))
                    break  # success — exit retry loop

                except asyncio.TimeoutError:
                    elapsed = time.monotonic() - t0
                    last_error = f"Timed out after {timeout_sec}s"
                    AGENT_DISPATCH_DURATION.labels(
                        agent_type=agent_key, status="timeout"
                    ).observe(elapsed)
                    if attempt < max_attempts:
                        AGENT_RETRY_TOTAL.labels(agent_type=agent_key).inc()
                    span.set_status(Status(StatusCode.ERROR, last_error))
                    logger.warning(
                        "agent.timeout",
                        agent=agent_key,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        timeout_sec=timeout_sec,
                        session_id=state["session_id"],
                    )

                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    last_error = str(exc)
                    AGENT_DISPATCH_DURATION.labels(
                        agent_type=agent_key, status="failed"
                    ).observe(elapsed)
                    if attempt < max_attempts:
                        AGENT_RETRY_TOTAL.labels(agent_type=agent_key).inc()
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, last_error))
                    logger.warning(
                        "agent.attempt_failed",
                        agent=agent_key,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=last_error,
                        session_id=state["session_id"],
                    )

            # Back-off between attempts (not after the last one).
            if attempt < max_attempts and result is None:
                sleep_for = min(backoff_sec * (2 ** (attempt - 1)), 30.0)
                await asyncio.sleep(sleep_for)

        # ── Retries exhausted ─────────────────────────────────────────────
        if result is None:
            if is_required:
                result = AgentResult(
                    task_id=node["task_id"],
                    agent_type=agent_key,
                    status=AgentResultStatus.FAILED,
                    error_message=last_error,
                )
                logger.error(
                    "agent.required_failed",
                    agent=agent_key,
                    error=last_error,
                    session_id=state["session_id"],
                )
            else:
                result = AgentResult(
                    task_id=node["task_id"],
                    agent_type=agent_key,
                    status=AgentResultStatus.PARTIAL,
                    output={"stub": True, "skipped": True, "reason": last_error},
                )
                AGENT_SKIP_TOTAL.labels(agent_type=agent_key).inc()
                logger.info(
                    "agent.optional_skipped",
                    agent=agent_key,
                    error=last_error,
                    session_id=state["session_id"],
                )

        # Record dashboard metrics for this invocation.
        total_elapsed = time.monotonic() - t_start
        agent_invocations_total.labels(agent_name=agent_key, outcome=result.status.value).inc()
        agent_duration_seconds.labels(agent_name=agent_key).observe(total_elapsed)

        # Emit terminal event.
        event_type = (
            AgentEventType.AGENT_COMPLETED
            if result.status == AgentResultStatus.COMPLETED
            else AgentEventType.AGENT_FAILED
        )
        self._emit(AgentEvent(
            event_type=event_type,
            session_id=state["session_id"],
            user_id=state["user_id"],
            correlation_id=state["request_id"],
            payload={
                "agent": agent_key,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "is_required": is_required,
            },
        ))
        return result

    def _emit(self, event: AgentEvent) -> None:
        self._events.emit(event)


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_context(
    node: TaskNode,
    state: OrchestratorState,
    prior_results: dict[str, AgentResult],
) -> AgentContext:
    raw_chunks = state.get("rag_chunks") or []
    rag_chunks = [
        RagChunk(
            chunk_id=c["chunk_id"],
            content=c["content"],
            source=c["source"],
            relevance_score=c["relevance_score"],
            title=c.get("title", ""),
            source_url=c.get("source_url"),
            metadata=c.get("metadata", {}),
        )
        for c in raw_chunks
    ]
    return AgentContext(
        task_id=node["task_id"],
        session_id=state["session_id"],
        user_id=state["user_id"],
        correlation_id=state["request_id"],
        stream_channel=state["stream_channel"],
        user_profile=state["user_profile"],
        user_message=state.get("user_message", ""),
        plan_snapshot={k: v.output for k, v in prior_results.items()},
        rag_chunks=rag_chunks,
    )


def _stub_result(node: TaskNode, reason: str) -> AgentResult:
    agent_key = node["agent_type"].value
    return AgentResult(
        task_id=node["task_id"],
        agent_type=agent_key,
        status=AgentResultStatus.PARTIAL,
        output={"stub": True, "message": reason},
    )


def _topological_phases(dag: list[TaskNode]) -> list[list[TaskNode]]:
    """Group DAG nodes into sequential phases using Kahn's algorithm.

    Nodes in the same phase have no inter-dependency and run in parallel.
    """
    task_by_id = {n["task_id"]: n for n in dag}
    in_degree: dict[str, int] = {n["task_id"]: 0 for n in dag}
    dependents: dict[str, list[str]] = {n["task_id"]: [] for n in dag}

    for node in dag:
        for dep in node["depends_on"]:
            in_degree[node["task_id"]] += 1
            dependents[dep].append(node["task_id"])

    phases: list[list[TaskNode]] = []
    ready = [tid for tid, deg in in_degree.items() if deg == 0]

    while ready:
        phase = [task_by_id[tid] for tid in ready]
        phases.append(phase)
        next_ready: list[str] = []
        for tid in ready:
            for dep_tid in dependents[tid]:
                in_degree[dep_tid] -= 1
                if in_degree[dep_tid] == 0:
                    next_ready.append(dep_tid)
        ready = next_ready

    return phases
