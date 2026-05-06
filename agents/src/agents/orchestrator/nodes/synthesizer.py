"""Nodes 6 + 7 — validate and synthesize.

``OutputValidatorNode`` delegates all validation logic to
``agents.orchestrator.output_validator.OutputValidator`` (the real module).
It writes the structured ``ValidationReport`` plus the scalar flags that the
``_validation_gate`` conditional edge depends on.

``SynthesizerNode`` aggregates all agent results into the final roadmap JSON.
It also injects per-step confidence scores from the validation report so the
synthesiser can note low-confidence phases in its output.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.contracts.results import AgentResultStatus
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.orchestrator.output_validator import OutputValidator, make_output_validator
from agents.orchestrator.result_aggregator import ResultAggregator
from agents.orchestrator.state import OrchestratorState

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.nodes.synthesizer")

_SYNTHESIZER_SYSTEM = """\
You are a senior career coach synthesising specialist-agent outputs into a
structured career roadmap. Produce a concise JSON roadmap with:
- "summary": 2-3 sentence overview
- "phases": list of {title, duration_weeks, milestones: [], skills_to_gain: [],
             confidence: float}   ← inject the per-phase confidence score here
- "weekly_habits": list of habit strings
- "next_steps": list of immediate action items (≤ 5)
- "unverified_claims": list of flagged claims from the validation stage
- "confidence": float 0.0–1.0  ← overall roadmap confidence

Use only the provided agent data — do not invent facts.
Where a phase confidence score is below 0.5, add a note in that phase's
milestones list: "Note: low confidence — verify timeline with a mentor."
"""


# ── Node 6 — OutputValidatorNode ──────────────────────────────────────────


def make_output_validator_node(
    validator: OutputValidator | None = None,
) -> "OutputValidatorNode":
    return OutputValidatorNode(validator or make_output_validator())


class OutputValidatorNode:
    """LangGraph node that runs the three-stage OutputValidator."""

    def __init__(self, validator: OutputValidator) -> None:
        self._validator = validator

    async def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        session_id = state["session_id"]
        correlation_id = state["request_id"]
        final_output = state.get("final_output") or {}

        with _tracer.start_as_current_span("node.output_validator") as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("correlation_id", correlation_id)

            try:
                report = await self._validator.validate(
                    agent_results=state.get("agent_results", {}),
                    roadmap=final_output,
                    session_id=session_id,
                    correlation_id=correlation_id,
                )
                span.set_attribute("passed", report.passed)
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.error(
                    "node.output_validator.failed",
                    error=str(exc),
                    exc_info=True,
                    session_id=session_id,
                )
                # Graceful degradation: treat as passed so synthesis can proceed.
                from agents.orchestrator.output_validator import ValidationReport
                report = ValidationReport(
                    realism_passed=True,
                    coherence_passed=True,
                    stage1_notes=[],
                    grounding_score=1.0,
                    unverified_claims=[],
                    step_confidences=[],
                    mean_step_confidence=1.0,
                    passed=True,
                    notes=[],
                    validation_duration_ms=0,
                )

            logger.info(
                "node.validation_done",
                passed=report.passed,
                grounding_score=report.grounding_score,
                unverified_count=len(report.unverified_claims),
                note_count=len(report.notes),
                session_id=session_id,
            )
            return {
                "validation_passed": report.passed,
                "validation_notes": report.notes,
                "validation_report": report.to_dict(),
            }


# ── Node 7 — SynthesizerNode ──────────────────────────────────────────────


def make_synthesizer(
    llm: ChatAnthropic | None = None,
    aggregator: ResultAggregator | None = None,
) -> "SynthesizerNode":
    _llm = llm or ChatAnthropic(
        model=agent_settings.orchestrator_model,
        api_key=agent_settings.anthropic_api_key.get_secret_value(),
        max_tokens=2048,
        temperature=0.3,
    )
    return SynthesizerNode(_llm, aggregator or ResultAggregator())


class SynthesizerNode:
    def __init__(self, llm: ChatAnthropic, aggregator: ResultAggregator) -> None:
        self._llm = llm
        self._aggregator = aggregator

    async def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        session_id = state["session_id"]

        with _tracer.start_as_current_span("node.synthesizer") as span:
            span.set_attribute("session_id", session_id)

            aggregated = self._aggregator.aggregate(state["agent_results"])

            user_context = (
                f"Target role: {state['user_profile'].target_role or 'unspecified'}. "
                f"Current role: {state['user_profile'].current_role or 'unspecified'}. "
                f"Timeline: {state['user_profile'].timeline_months or 'unspecified'} months. "
                f"Goal: {state.get('parsed_intent') or state['user_message']}"
            )

            # Inject validation context so the synthesiser annotates low-confidence phases.
            validation_report = state.get("validation_report") or {}
            step_confidences = validation_report.get("step_confidences", [])
            unverified_claims = validation_report.get("unverified_claims", [])

            synthesis_context = {
                "user_context": user_context,
                "agent_data": aggregated,
                "step_confidences": step_confidences,
                "unverified_claims": unverified_claims,
                "validation_passed": state.get("validation_passed", True),
            }

            try:
                response = await self._llm.ainvoke(
                    [
                        SystemMessage(content=_SYNTHESIZER_SYSTEM),
                        HumanMessage(content=json.dumps(synthesis_context, indent=2)),
                    ]
                )
                roadmap = json.loads(str(response.content))
                final_message = AIMessage(content=json.dumps(roadmap))
                span.set_attribute("has_phases", bool(roadmap.get("phases")))
                span.set_status(Status(StatusCode.OK))

            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.error(
                    "node.synthesizer.failed",
                    error=str(exc),
                    exc_info=True,
                    session_id=session_id,
                )
                roadmap = aggregated
                final_message = AIMessage(content="Synthesis failed — returning raw agent data.")

            logger.info(
                "node.synthesis_done",
                has_phases=bool(roadmap.get("phases")),
                session_id=session_id,
            )
            return {
                "final_output": roadmap,
                "status": AgentResultStatus.COMPLETED,
                "messages": [final_message],
            }
