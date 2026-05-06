"""Node 3 — build_dag.

Delegates to ``TaskPlanner`` to build an execution DAG for the current
intent type. The DAG tells the dispatcher which agents to run, in what
order, and which can run in parallel.
"""
from agents.core.logging import get_logger
from agents.orchestrator.state import OrchestratorState, TaskNode
from agents.orchestrator.task_planner import TaskPlanner

logger = get_logger(__name__)


def make_dag_builder(planner: TaskPlanner | None = None) -> "DagBuilderNode":
    _planner = planner or TaskPlanner()
    return DagBuilderNode(_planner)


class DagBuilderNode:
    def __init__(self, planner: TaskPlanner) -> None:
        self._planner = planner

    async def __call__(self, state: OrchestratorState) -> dict:
        intent_type = state.get("intent_type", "roadmap_generation")
        dag: list[TaskNode] = self._planner.build(
            intent_type=intent_type,
            user_profile=state["user_profile"],
            correlation_id=state["request_id"],
        )
        logger.info(
            "node.dag_built",
            intent_type=intent_type,
            node_count=len(dag),
            session_id=state["session_id"],
        )
        return {"task_dag": dag}
