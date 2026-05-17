"""TaskPlanner — builds the agent execution DAG from an intent type.

The planner decides which agents to invoke, what data each needs, which
can run concurrently, and what retry/fallback behaviour each should use.
It encodes the dependency graph as a list of ``TaskNode`` objects (defined
in ``state.py``).

DAG structure for ``roadmap_generation`` (the most complex intent):
  Phase 1 (parallel): INTAKE, CV_ANALYSIS, MARKET_INTELLIGENCE
  Phase 2 (serial):   GAP_ANALYSIS        (needs INTAKE + CV results)
  Phase 3 (serial):   ROADMAP_GENERATION  (needs gap + market)
  Phase 4 (parallel): LEARNING_RESOURCES, NETWORKING, OPPORTUNITY

Simpler intents use a sub-graph of the same agents.
"""
from __future__ import annotations

from opentelemetry.trace import Status, StatusCode
from uuid import uuid4

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.orchestrator.state import TaskNode

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.task_planner")

# ── Per-agent retry and fallback specifications ─────────────────────────────
# ``is_required=True``  → failure causes OrchestratorResult.status = FAILED.
# ``is_required=False`` → failure causes PARTIAL result; synthesis continues.
# ``retry_policy`` keys are read directly by AgentDispatcherNode.

_AGENT_SPECS: dict[AgentType, dict] = {
    AgentType.INTAKE: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 30, "backoff_seconds": 1.0},
    },
    AgentType.CV_ANALYSIS: {
        "is_required": True,
        "retry_policy": {"max_attempts": 3, "timeout_seconds": 60, "backoff_seconds": 2.0},
    },
    AgentType.MARKET_INTELLIGENCE: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 90, "backoff_seconds": 3.0},
    },
    AgentType.GAP_ANALYSIS: {
        "is_required": True,
        "retry_policy": {"max_attempts": 3, "timeout_seconds": 120, "backoff_seconds": 2.0},
    },
    AgentType.ROADMAP_GENERATION: {
        "is_required": True,
        "retry_policy": {"max_attempts": 3, "timeout_seconds": 120, "backoff_seconds": 4.0},
    },
    AgentType.LEARNING_RESOURCES: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 60, "backoff_seconds": 2.0},
    },
    AgentType.NETWORKING: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 45, "backoff_seconds": 2.0},
    },
    AgentType.OPPORTUNITY: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 60, "backoff_seconds": 2.0},
    },
    AgentType.PROGRESS: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 45, "backoff_seconds": 2.0},
    },
    AgentType.COACH: {
        "is_required": True,
        "retry_policy": {"max_attempts": 3, "timeout_seconds": 90, "backoff_seconds": 3.0},
    },
    AgentType.VALIDATOR: {
        "is_required": False,
        "retry_policy": {"max_attempts": 2, "timeout_seconds": 60, "backoff_seconds": 2.0},
    },
}

_DEFAULT_SPEC: dict = {
    "is_required": False,
    "retry_policy": {"max_attempts": 2, "timeout_seconds": 60, "backoff_seconds": 2.0},
}

# ── DAG templates ───────────────────────────────────────────────────────────
# Each entry: (agent_type, [dependency_agent_types]).
# Phase numbers are computed automatically from the dependency graph.

_DAG_TEMPLATES: dict[str, list[tuple[AgentType, list[AgentType]]]] = {
    # INTAKE, CV_ANALYSIS, and MARKET_INTELLIGENCE run in parallel at phase 1.
    # GAP_ANALYSIS waits for both INTAKE (NER-extracted profile slots) and
    # CV_ANALYSIS (structured CV gaps) before proceeding.
    "roadmap_generation": [
        (AgentType.INTAKE,              []),
        (AgentType.CV_ANALYSIS,         []),
        (AgentType.MARKET_INTELLIGENCE, []),
        (AgentType.GAP_ANALYSIS,        [AgentType.CV_ANALYSIS, AgentType.INTAKE]),
        (AgentType.ROADMAP_GENERATION,  [AgentType.GAP_ANALYSIS, AgentType.MARKET_INTELLIGENCE]),
        (AgentType.LEARNING_RESOURCES,  [AgentType.ROADMAP_GENERATION]),
        (AgentType.NETWORKING,          [AgentType.ROADMAP_GENERATION]),
        (AgentType.OPPORTUNITY,         [AgentType.ROADMAP_GENERATION]),
    ],
    "cv_review": [
        (AgentType.INTAKE,      []),
        (AgentType.CV_ANALYSIS, [AgentType.INTAKE]),
        (AgentType.GAP_ANALYSIS, [AgentType.CV_ANALYSIS]),
    ],
    "market_query": [
        (AgentType.MARKET_INTELLIGENCE, []),
    ],
    "coach_query": [
        (AgentType.COACH, []),
    ],
    "progress_review": [
        (AgentType.PROGRESS, []),
    ],
    "opportunity_search": [
        (AgentType.OPPORTUNITY, []),
    ],
}

_DEFAULT_INTENT = "roadmap_generation"


class TaskPlanner:
    """Stateless DAG builder — one instance shared across all orchestrator runs."""

    def build(
        self,
        intent_type: str,
        user_profile: UserProfileSnapshot,
        correlation_id: str,
    ) -> list[TaskNode]:
        """Return a list of ``TaskNode`` objects representing the execution DAG.

        Each node carries its retry policy and required-flag so the dispatcher
        can act on them without consulting the planner again.
        """
        with _tracer.start_as_current_span("task_planner.build") as span:
            span.set_attribute("intent_type", intent_type)
            span.set_attribute("correlation_id", correlation_id)

            template = _DAG_TEMPLATES.get(intent_type)
            if template is None:
                logger.warning(
                    "task_planner.unknown_intent",
                    intent_type=intent_type,
                    fallback=_DEFAULT_INTENT,
                )
                template = _DAG_TEMPLATES[_DEFAULT_INTENT]
                intent_type = _DEFAULT_INTENT

            # Stable task IDs: correlation_id:agent_type so sub-tasks are traceable
            task_ids: dict[AgentType, str] = {
                agent_type: f"{correlation_id}:{agent_type.value}"
                for agent_type, _ in template
            }

            # Compute the phase number for each agent via Kahn's algorithm on
            # the template's dependency graph.
            phases = _compute_phases(template)

            dag: list[TaskNode] = []
            for agent_type, deps in template:
                # Skip PROGRESS when no existing plan exists.
                if agent_type == AgentType.PROGRESS and not user_profile.additional.get(
                    "has_existing_plan"
                ):
                    continue

                spec = _AGENT_SPECS.get(agent_type, _DEFAULT_SPEC)
                phase = phases.get(agent_type, 1)

                node = TaskNode(
                    task_id=task_ids[agent_type],
                    agent_type=agent_type,
                    depends_on=[task_ids[dep] for dep in deps if dep in task_ids],
                    can_run_parallel=len(deps) == 0
                    or all(dep in task_ids for dep in deps),
                    phase=phase,
                    is_required=spec["is_required"],
                    retry_policy=spec["retry_policy"],
                )
                dag.append(node)

            span.set_attribute("dag_size", len(dag))
            span.set_attribute("phases", max(phases.values(), default=1))
            span.set_attribute(
                "required_agents",
                ",".join(n["agent_type"].value for n in dag if n["is_required"]),
            )
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "task_planner.dag_built",
                intent_type=intent_type,
                agents=[n["agent_type"].value for n in dag],
                phases=max((n["phase"] for n in dag), default=1),
                required=[n["agent_type"].value for n in dag if n["is_required"]],
                correlation_id=correlation_id,
            )
            return dag


# ── Helpers ─────────────────────────────────────────────────────────────────


def _compute_phases(
    template: list[tuple[AgentType, list[AgentType]]],
) -> dict[AgentType, int]:
    """Assign a 1-based phase number to each agent using BFS on the DAG.

    All agents with no dependencies are Phase 1. Agents whose dependencies
    are all in Phase N are Phase N+1. This matches the topological ordering
    used by the dispatcher so ``phase`` is always consistent with execution order.
    """
    phase: dict[AgentType, int] = {}
    deps_map = {agent: list(deps) for agent, deps in template}

    changed = True
    while changed:
        changed = False
        for agent, deps in deps_map.items():
            if not deps:
                new_phase = 1
            else:
                # Phase = max of all dependency phases + 1
                dep_phases = [phase.get(d, 0) for d in deps]
                if 0 in dep_phases:
                    continue  # dependency not yet resolved
                new_phase = max(dep_phases) + 1

            if phase.get(agent) != new_phase:
                phase[agent] = new_phase
                changed = True

    return phase
