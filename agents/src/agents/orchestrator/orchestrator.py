"""MasterOrchestrator — LangGraph StateGraph wiring the 8-step ReAct pipeline.

Pipeline (matches architecture doc exactly):
  1. parse_intent          — extract user goal & intent type
  2. score_completeness    — check profile completeness
     ↓ if incomplete & rounds < max → emit clarification event, return early
     ↓ if complete (or max rounds reached) → continue
  3. build_dag             — build execution DAG from intent type
  4. dispatch_and_collect  — run agents in parallel; collect results
  5. synthesize            — merge results into final roadmap
  6. validate              — quality-check synthesized roadmap (3-stage: realism, grounding, confidence)
  7. deliver               — emit terminal event; return OrchestratorResult

Each pipeline step emits a STEP_PROGRESS event so the client can render a
progress bar. The step wrapping is done at graph-construction time via the
module-level ``_with_progress`` helper so individual nodes remain clean.

The orchestrator is stateless after ``run()`` returns — all session state
is managed by the caller (the Celery task in ``agents.bus.tasks``).
"""
from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import uuid4

import redis
import structlog
from langgraph.graph import END, StateGraph

from agents.bus.channel import channel_for_session
from agents.bus.publisher import EventPublisher
from agents.config import agent_settings
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.results import AgentResultStatus, OrchestratorResult
from agents.contracts.tasks import OrchestratorTaskInput
from agents.core.logging import get_logger
from agents.core.observability import STEP_PROGRESS_TOTAL, get_tracer
from agents.orchestrator.clarification_engine import ClarificationEngine
from agents.orchestrator.nodes.agent_dispatcher import make_agent_dispatcher
from agents.orchestrator.nodes.completeness_scorer import make_completeness_scorer
from agents.orchestrator.nodes.dag_builder import make_dag_builder
from agents.orchestrator.nodes.intent_parser import make_intent_parser
from agents.orchestrator.nodes.synthesizer import (
    make_output_validator_node,
    make_synthesizer,
)
from agents.orchestrator.output_validator import make_output_validator
from agents.orchestrator.result_aggregator import ResultAggregator
from agents.orchestrator.state import OrchestratorState
from agents.orchestrator.task_planner import TaskPlanner
from agents.persistence.interfaces import IRoadmapStore
from agents.persistence.noop_store import NoOpRoadmapStore

# RAG imports are optional — if keys are missing the node returns [] gracefully.
try:
    from agents.rag.ingestion.embedder import OpenAIEmbedder
    from agents.rag.retrieval.context_assembler import ContextAssembler
    from agents.rag.retrieval.hyde import get_hyde_expander
    from agents.rag.retrieval.query_cache import get_rag_cache
    from agents.rag.retrieval.retriever import PineconeRetriever

    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator")

# Step registry — order must match graph topology.
_PIPELINE_STEPS = [
    "parse_intent",
    "score_completeness",
    "build_dag",
    "initialize_roadmap",
    "assemble_rag_context",
    "dispatch_and_collect",
    "synthesize",
    "validate",
]
_TOTAL_STEPS = len(_PIPELINE_STEPS)


class MasterOrchestrator:
    """Assembles and executes the LangGraph orchestration pipeline.

    One instance is created per Celery task invocation. All dependencies
    (LLM clients, publishers, planners) are constructed here so that the
    Celery task stays thin and the orchestrator is independently testable.
    """

    def __init__(self, store: IRoadmapStore | None = None) -> None:
        # Synchronous Redis client for event publishing (Celery worker context)
        self._redis = redis.from_url(
            str(agent_settings.redis_url), decode_responses=True
        )
        self._event_publisher = EventPublisher(self._redis)
        self._clarification_engine = ClarificationEngine()
        self._task_planner = TaskPlanner()
        self._result_aggregator = ResultAggregator()
        self._store: IRoadmapStore = store or NoOpRoadmapStore()

        # Build node instances
        _validator = make_output_validator()
        self._intent_parser = make_intent_parser()
        self._completeness_scorer = make_completeness_scorer(self._clarification_engine)
        self._dag_builder = make_dag_builder(self._task_planner)
        self._rag_assembler_node = _make_rag_assembler_node()
        self._agent_dispatcher = make_agent_dispatcher(self._event_publisher, self._store)
        self._output_validator = make_output_validator_node(_validator)
        self._synthesizer = make_synthesizer(aggregator=self._result_aggregator)

        # Compile the LangGraph graph once at construction
        self._graph = self._build_graph()

    # ── Public entry-point ────────────────────────────────────────────────────

    async def run(self, task_input: OrchestratorTaskInput) -> OrchestratorResult:
        """Execute the full pipeline. Returns a fully populated result."""
        start = time.monotonic()
        log = logger.bind(
            request_id=task_input.request_id,
            user_id=task_input.user_id,
            session_id=task_input.session_id,
        )
        log.info("orchestrator.started")

        self._emit(AgentEvent(
            event_type=AgentEventType.ORCHESTRATION_STARTED,
            session_id=task_input.session_id,
            user_id=task_input.user_id,
            correlation_id=task_input.request_id,
            payload={"request_id": task_input.request_id},
        ))

        try:
            initial_state: OrchestratorState = {
                "request_id": task_input.request_id,
                "session_id": task_input.session_id,
                "user_id": task_input.user_id,
                "stream_channel": task_input.stream_channel,
                "user_message": task_input.user_message,
                "user_profile": task_input.user_profile,
                "messages": [],
                "forced_intent": task_input.forced_intent,
                "parsed_intent": None,
                "intent_type": None,
                "completeness_score": 0.0,
                "missing_slots": [],
                # Carry forward round counter and previous questions for
                # multi-turn clarification answer parsing.
                "clarification_round": task_input.clarification_round,
                "clarification_questions": task_input.previous_clarification_questions,
                "task_dag": [],
                "roadmap_id": None,
                "rag_chunks": [],
                "agent_results": {},
                "validation_passed": False,
                "validation_notes": [],
                "validation_report": None,
                "final_output": None,
                "status": AgentResultStatus.COMPLETED,
                "error_message": None,
            }

            config = {"recursion_limit": agent_settings.orchestrator_max_iterations}
            final_state: OrchestratorState = await self._graph.ainvoke(
                initial_state, config=config
            )

            duration_ms = int((time.monotonic() - start) * 1000)

            # Clarification was required and the graph returned early
            if final_state.get("clarification_questions"):
                return self._clarification_result(final_state, task_input, duration_ms)

            final_output = final_state.get("final_output") or {}
            result = OrchestratorResult(
                request_id=task_input.request_id,
                session_id=task_input.session_id,
                user_id=task_input.user_id,
                status=final_state.get("status", AgentResultStatus.COMPLETED),
                roadmap=final_output or None,
                roadmap_id=final_state.get("roadmap_id"),
                agent_results=final_state.get("agent_results", {}),
                confidence=final_output.get("confidence", 1.0),
                validation_passed=final_state.get("validation_passed", True),
                error_message=final_state.get("error_message"),
                duration_ms=duration_ms,
            )

            self._emit(AgentEvent(
                event_type=AgentEventType.ORCHESTRATION_COMPLETED,
                session_id=task_input.session_id,
                user_id=task_input.user_id,
                correlation_id=task_input.request_id,
                payload=result.model_dump(mode="json"),
            ))
            log.info("orchestrator.completed", duration_ms=duration_ms)
            return result

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error("orchestrator.failed", error=str(exc), exc_info=True)
            self._emit(AgentEvent(
                event_type=AgentEventType.ORCHESTRATION_FAILED,
                session_id=task_input.session_id,
                user_id=task_input.user_id,
                correlation_id=task_input.request_id,
                payload={"error": str(exc)},
            ))
            return OrchestratorResult(
                request_id=task_input.request_id,
                session_id=task_input.session_id,
                user_id=task_input.user_id,
                status=AgentResultStatus.FAILED,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            self._redis.close()

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(OrchestratorState)

        # Wrap every node with a STEP_PROGRESS emitter; node names are unchanged.
        steps = [
            ("parse_intent",          self._intent_parser),
            ("score_completeness",    self._completeness_scorer),
            ("build_dag",             self._dag_builder),
            ("initialize_roadmap",    self._initialize_roadmap_node()),
            ("assemble_rag_context",  self._rag_assembler_node),
            ("dispatch_and_collect",  self._agent_dispatcher),
            ("synthesize",            self._synthesizer),
            ("validate",              self._output_validator),
        ]
        for idx, (name, fn) in enumerate(steps):
            graph.add_node(name, _with_progress(fn, name, idx, _TOTAL_STEPS, self._emit))

        # Linear edges
        graph.set_entry_point("parse_intent")
        graph.add_edge("parse_intent", "score_completeness")

        # Conditional: proceed or surface clarification questions
        graph.add_conditional_edges(
            "score_completeness",
            _should_clarify,
            {
                "clarify": END,         # Return early; API surfaces the questions
                "proceed": "build_dag",
            },
        )

        graph.add_edge("build_dag", "initialize_roadmap")
        graph.add_edge("initialize_roadmap", "assemble_rag_context")
        graph.add_edge("assemble_rag_context", "dispatch_and_collect")
        graph.add_edge("dispatch_and_collect", "synthesize")

        # Synthesize first, then validate the generated roadmap.
        graph.add_edge("synthesize", "validate")

        # Validation outcome never blocks delivery — lower confidence is annotated
        # in the roadmap, not used to gate the response.
        graph.add_conditional_edges(
            "validate",
            _validation_gate,
            {
                "pass": END,
                "fail": END,
            },
        )

        return graph.compile()

    def _initialize_roadmap_node(self):
        """Return an async node that creates the Firestore skeleton and writes roadmap_id to state."""
        store = self._store

        async def _initialize_roadmap(state: OrchestratorState) -> dict:
            try:
                roadmap_id = await store.create_skeleton(
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    request_id=state["request_id"],
                )
            except Exception as exc:
                logger.warning("orchestrator.init_roadmap_failed", error=str(exc))
                roadmap_id = None
            return {"roadmap_id": roadmap_id}

        return _initialize_roadmap

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clarification_result(
        self,
        state: OrchestratorState,
        task_input: OrchestratorTaskInput,
        duration_ms: int,
    ) -> OrchestratorResult:
        questions = state.get("clarification_questions", [])
        self._emit(AgentEvent(
            event_type=AgentEventType.CLARIFICATION_REQUIRED,
            session_id=task_input.session_id,
            user_id=task_input.user_id,
            correlation_id=task_input.request_id,
            payload={
                "questions": questions,
                "round": state.get("clarification_round", 1),
            },
        ))
        return OrchestratorResult(
            request_id=task_input.request_id,
            session_id=task_input.session_id,
            user_id=task_input.user_id,
            status=AgentResultStatus.PARTIAL,
            clarification_required=True,
            clarification_questions=questions,
            duration_ms=duration_ms,
        )

    def _emit(self, event: AgentEvent) -> None:
        self._event_publisher.emit(event)


# ── Step-progress wrapping ────────────────────────────────────────────────────


def _with_progress(
    node_fn: Callable[[OrchestratorState], Coroutine[Any, Any, dict]],
    step_name: str,
    step_index: int,
    total_steps: int,
    emit: Callable[[AgentEvent], None],
) -> Callable[[OrchestratorState], Coroutine[Any, Any, dict]]:
    """Return an async callable that emits STEP_PROGRESS before delegating."""

    async def _wrapper(state: OrchestratorState) -> dict:
        emit(AgentEvent(
            event_type=AgentEventType.STEP_PROGRESS,
            session_id=state["session_id"],
            user_id=state["user_id"],
            correlation_id=state["request_id"],
            payload={
                "step_name": step_name,
                "step_index": step_index,
                "total_steps": total_steps,
                "pct": round((step_index / total_steps) * 100),
            },
        ))
        STEP_PROGRESS_TOTAL.labels(step_name=step_name).inc()
        return await node_fn(state)

    return _wrapper


# ── Conditional edge functions ────────────────────────────────────────────────


def _should_clarify(state: OrchestratorState) -> str:
    """Return 'clarify' when the profile is incomplete and questions were generated.

    ``clarification_round`` has already been incremented by the scorer node,
    so a value of 1 means this is the first clarification request.
    """
    score = state.get("completeness_score", 0.0)
    questions = state.get("clarification_questions", [])
    round_num = state.get("clarification_round", 1)

    needs_clarification = (
        score < agent_settings.completeness_threshold
        and bool(questions)
        and round_num <= agent_settings.max_clarification_rounds
    )
    return "clarify" if needs_clarification else "proceed"


def _validation_gate(state: OrchestratorState) -> str:
    return "pass" if state.get("validation_passed", True) else "fail"


# ── RAG context assembler node ────────────────────────────────────────────────


def _make_rag_assembler_node() -> "Callable[[OrchestratorState], Coroutine[Any, Any, dict]]":
    """Return the assemble_rag_context node function.

    If RAG is unavailable (missing packages or keys), the node returns an
    empty rag_chunks list so the pipeline continues unaffected.
    """
    assembler: "ContextAssembler | None" = None

    if _RAG_AVAILABLE and agent_settings.rag_enabled:
        try:
            _embedder = OpenAIEmbedder()
            _retriever = PineconeRetriever(embedder=_embedder)
            _hyde = get_hyde_expander() if agent_settings.hyde_enabled else None
            _cache = get_rag_cache() if agent_settings.rag_cache_enabled else None
            assembler = ContextAssembler(
                retriever=_retriever,
                hyde_expander=_hyde,
                cache=_cache,
            )
            logger.info(
                "rag.assembler.initialised",
                hyde=agent_settings.hyde_enabled,
                cache=agent_settings.rag_cache_enabled,
            )
        except Exception as exc:
            logger.warning("rag.assembler.init_failed", error=str(exc))

    async def _assemble_rag_context(state: OrchestratorState) -> dict:
        if assembler is None:
            return {"rag_chunks": []}
        chunks = await assembler.assemble(
            user_message=state.get("user_message", ""),
            user_profile=state["user_profile"],
            intent_type=state.get("intent_type"),
        )
        return {
            "rag_chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "content": c.content,
                    "source": c.source,
                    "relevance_score": c.relevance_score,
                    "title": c.title,
                    "source_url": c.source_url,
                    "metadata": dict(c.metadata),
                }
                for c in chunks
            ]
        }

    return _assemble_rag_context
