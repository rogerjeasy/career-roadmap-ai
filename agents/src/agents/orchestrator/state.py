"""OrchestratorState — typed state threaded through the LangGraph graph.

LangGraph merges partial dict updates from each node into this state.
Only fields that must survive node transitions live here; ephemeral
computation stays local to the node function.

The ``messages`` field uses LangGraph's built-in ``add_messages`` reducer
so that each node can append without overwriting prior turns.
"""
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agents.contracts.results import AgentResult, AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot


class TaskNode(TypedDict):
    """A node in the execution DAG built by ``TaskPlanner``.

    ``retry_policy`` is stored as a plain dict so it survives LangGraph's
    JSON serialisation checkpoints.  Keys: max_attempts (int),
    timeout_seconds (int), backoff_seconds (float).
    """

    task_id: str
    agent_type: AgentType
    # task_ids this node must wait for before it can start
    depends_on: list[str]
    # True if this node can run in parallel with its phase siblings
    can_run_parallel: bool
    # 1-based execution phase (all nodes in the same phase run concurrently)
    phase: int
    # False → failure produces PARTIAL result, not FAILED; synthesis continues
    is_required: bool
    # Retry / timeout parameters read by AgentDispatcherNode
    retry_policy: dict[str, Any]


class OrchestratorState(TypedDict):
    """Complete mutable state for one orchestration run.

    Fields prefixed with ``_`` are internal bookkeeping and should not
    be included in the final ``OrchestratorResult``.
    """

    # ── Immutable inputs (set once at entry) ─────────────────
    request_id: str
    session_id: str
    user_id: str
    stream_channel: str
    user_message: str
    user_profile: UserProfileSnapshot

    # ── Conversation history ──────────────────────────────────
    # ``add_messages`` reducer appends rather than replaces on each node update
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Intent parsing (Node 1) ───────────────────────────────
    # When forced_intent is set at entry, the intent parser skips LLM detection.
    forced_intent: str | None
    parsed_intent: str | None
    intent_type: str | None  # e.g. "roadmap_generation", "coach_query", "cv_review"

    # ── Completeness scoring (Node 2) ─────────────────────────
    completeness_score: float
    missing_slots: list[str]
    clarification_round: int
    clarification_questions: list[dict[str, Any]]

    # ── Task planning (Node 3) ────────────────────────────────
    task_dag: list[TaskNode]

    # ── Agent dispatch + collection (Nodes 4–5) ───────────────
    agent_results: dict[str, AgentResult]  # keyed by AgentType value

    # ── Validation (Node 6) ───────────────────────────────────
    validation_passed: bool
    validation_notes: list[str]
    # Full structured report from OutputValidator.validate(); stored as dict
    # so it round-trips through LangGraph's JSON serialisation checkpoints.
    validation_report: dict[str, Any] | None

    # ── Synthesis (Node 7) ────────────────────────────────────
    final_output: dict[str, Any] | None

    # ── Terminal state ────────────────────────────────────────
    status: AgentResultStatus
    error_message: str | None
