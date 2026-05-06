"""Node 2 — score_completeness.

On every invocation this node:
1. (Round > 0 only) Parses the user's reply to the previous clarification
   questions and applies any extracted values onto the profile snapshot.
2. Scores the (potentially updated) profile for completeness.
3. Generates targeted follow-up questions when the score is below threshold
   and the round cap has not been reached.

The node then writes its results back into state so the conditional edge can
decide whether to route to ``build_dag`` (proceed) or return early (clarify).
"""
from __future__ import annotations

from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.orchestrator.clarification_engine import (
    ClarificationEngine,
    ClarificationQuestion,
)
from agents.orchestrator.state import OrchestratorState

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.nodes.completeness_scorer")


def make_completeness_scorer(
    engine: ClarificationEngine | None = None,
) -> CompletenessScorerNode:
    return CompletenessScorerNode(engine or ClarificationEngine())


class CompletenessScorerNode:
    """LangGraph node that drives the clarification loop."""

    def __init__(self, engine: ClarificationEngine) -> None:
        self._engine = engine

    async def __call__(self, state: OrchestratorState) -> dict:
        request_id = state["request_id"]
        session_id = state["session_id"]
        current_round = state.get("clarification_round", 0)
        profile = state["user_profile"]

        with _tracer.start_as_current_span("node.completeness_scorer") as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("clarification_round", current_round)

            # ── Step 1: parse & apply answers from the previous round ─────
            applied_fields: list[str] = []
            if current_round > 0:
                previous_qs_raw = state.get("clarification_questions", [])
                user_reply = state.get("user_message", "")

                if previous_qs_raw and user_reply:
                    previous_questions = [
                        ClarificationQuestion.from_dict(q) for q in previous_qs_raw
                    ]
                    parsed = await self._engine.parse_answers(
                        previous_questions,
                        user_reply,
                        correlation_id=request_id,
                    )
                    if parsed:
                        profile, applied_fields = self._engine.apply_answers(
                            profile,
                            parsed,
                            correlation_id=request_id,
                        )
                        logger.info(
                            "node.answers_applied",
                            applied=applied_fields,
                            session_id=session_id,
                            round=current_round,
                        )

            span.set_attribute("fields_applied", ",".join(applied_fields))

            # ── Step 2: score the (updated) profile ───────────────────────
            score, missing = self._engine.score(profile, correlation_id=request_id)

            logger.info(
                "node.completeness_scored",
                score=score,
                missing=missing,
                round=current_round,
                session_id=session_id,
                threshold=agent_settings.completeness_threshold,
            )

            # ── Step 3: generate questions if still incomplete ────────────
            questions: list[ClarificationQuestion] = []
            next_round = current_round + 1  # increment regardless of outcome

            needs_questions = (
                score < agent_settings.completeness_threshold
                and current_round < agent_settings.max_clarification_rounds
                and bool(missing)
            )
            if needs_questions:
                questions = await self._engine.generate_questions(
                    profile=profile,
                    missing_slots=missing,
                    user_message=state.get("user_message", ""),
                    correlation_id=request_id,
                    intent_type=state.get("intent_type") or "unknown",
                )

            span.set_attribute("questions_count", len(questions))
            span.set_attribute("score", score)
            span.set_status(Status(StatusCode.OK))

            return {
                # Updated profile may carry newly extracted values.
                "user_profile": profile,
                "completeness_score": score,
                "missing_slots": missing,
                # Advance the round counter so the next invocation knows its position.
                "clarification_round": next_round,
                # Serialise as dicts to remain compatible with the TypedDict state.
                "clarification_questions": [q.to_dict() for q in questions],
            }
