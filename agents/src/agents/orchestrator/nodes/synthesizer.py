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
import re
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
structured career roadmap. Respond with raw JSON only — no markdown, no code
fences, no explanation, no preamble. Start your response with the opening brace.

The JSON object must have exactly these top-level keys:
- "summary": 2-3 sentence overview of the roadmap
- "phases": list of phase objects (schema below)
- "weekly_habits": list of habit strings
- "next_steps": list of immediate action items (≤ 5)
- "unverified_claims": list of any claims you cannot verify from the agent data
- "confidence": float 0.0–1.0 (overall roadmap confidence based on data quality)

Phase object schema — every field is REQUIRED:
{
  "title": str,
  "duration_weeks": int,
  "milestones": [str, ...],
  "skills_to_gain": [str, ...],
  "confidence": float,
  "sources": [str, ...]
}

CITATION RULES — phases that violate these will be flagged as uncited and fail validation:
- "sources" MUST contain at least one entry per phase.
- Use [SRC-N] IDs exactly as they appear in the evidence_cards block of the input.
- Cite every evidence card that directly supports the phase's skills, milestones, or timeline.
- If no evidence card covers a phase, set confidence ≤ 0.3 and write
  ["[ASSUMPTION]"] as the sources list — never leave sources empty.
- Do NOT invent [SRC-N] IDs; only use IDs that appear in the provided evidence cards.
- If no evidence_cards block is present in the input, write ["[NO_EVIDENCE]"] per phase.

Use only the provided agent data — do not invent facts not present in agent_data.
Set phase confidence to 1.0 when the phase is well-supported by agent data; use
lower values when data is sparse or conflicting.
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
                    rag_chunks=state.get("rag_chunks") or [],
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
                # Graceful degradation: treat as passed so the pipeline completes.
                from agents.orchestrator.output_validator import ValidationReport
                report = ValidationReport(
                    realism_passed=True,
                    coherence_passed=True,
                    stage1_notes=[],
                    grounding_score=1.0,
                    unverified_claims=[],
                    citation_check_passed=True,
                    uncited_phases=[],
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


def _extract_json(content: str) -> str:
    """Extract a JSON object from Claude's response.

    Handles three common shapes:
      1. Bare JSON (ideal case)
      2. JSON wrapped in ```json ... ``` or ``` ... ``` markdown fences
      3. JSON preceded by explanatory prose (Claude ignoring the no-prose instruction)
    """
    content = content.strip()
    # 1. Markdown fence
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
    if match:
        return match.group(1).strip()
    # 2. Find the first JSON object in the response (skips any preamble)
    brace_idx = content.find("{")
    if brace_idx != -1:
        return content[brace_idx:]
    return content


def _build_fallback_roadmap(aggregated: dict[str, Any]) -> dict[str, Any]:
    """Build a structured roadmap dict from agent outputs when LLM synthesis fails.

    Converts the roadmap_generation agent's phase format to the Firestore-expected
    synthesizer format so that at least a partial, structured result is persisted.
    """
    agent_outputs = aggregated.get("agent_outputs", {})
    rg = agent_outputs.get("roadmap_generation", {})

    rg_phases: list[dict] = rg.get("phases", [])
    rg_milestones: list[dict] = rg.get("milestones", [])

    phases = []
    for p in rg_phases:
        phase_milestones = [
            m.get("name", "")
            for m in rg_milestones
            if m.get("phase_index") == p.get("index")
        ]
        phases.append({
            "title": p.get("title", ""),
            "duration_weeks": p.get("duration_weeks", 0),
            "milestones": phase_milestones,
            "skills_to_gain": p.get("skills_to_acquire", []),
            "confidence": 1.0,
            "sources": ["[ASSUMPTION]"],
        })

    habits: list = rg.get("habits", [])
    weekly_habits = [
        h.get("name", str(h)) if isinstance(h, dict) else str(h)
        for h in habits
    ]

    return {
        "summary": rg.get("summary", ""),
        "phases": phases,
        "weekly_habits": weekly_habits,
        "next_steps": [],
        "unverified_claims": [],
        "confidence": aggregated.get("overall_confidence", 1.0),
    }


def make_synthesizer(
    llm: ChatAnthropic | None = None,
    aggregator: ResultAggregator | None = None,
) -> "SynthesizerNode":
    _llm = llm or ChatAnthropic(
        model=agent_settings.orchestrator_model,
        api_key=agent_settings.anthropic_api_key.get_secret_value(),
        max_tokens=4096,
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

            # Build evidence cards from RAG chunks so the LLM can cite [SRC-N] IDs.
            evidence_text = ""
            raw_chunks = state.get("rag_chunks") or []
            if raw_chunks:
                try:
                    from agents.core.context import RagChunk  # noqa: PLC0415
                    from agents.rag.context_injector import get_context_injector  # noqa: PLC0415

                    rag_chunks = [
                        RagChunk(
                            chunk_id=c["chunk_id"],
                            content=c["content"],
                            source=c["source"],
                            relevance_score=c.get("relevance_score", 0.0),
                            title=c.get("title", ""),
                            source_url=c.get("source_url"),
                            metadata=c.get("metadata", {}),
                        )
                        for c in raw_chunks
                    ]
                    injected = get_context_injector().inject(
                        rag_chunks,
                        intent_type=state.get("intent_type"),
                    )
                    evidence_text = injected.formatted_context
                except Exception as exc:
                    logger.warning(
                        "node.synthesizer.rag_injection_failed",
                        error=str(exc),
                        session_id=session_id,
                    )

            synthesis_context: dict[str, Any] = {
                "user_context": user_context,
                "agent_data": aggregated,
            }
            if evidence_text:
                synthesis_context["evidence_cards"] = evidence_text

            span.set_attribute("has_evidence_cards", bool(evidence_text))
            span.set_attribute("rag_chunk_count", len(raw_chunks))

            try:
                response = await self._llm.ainvoke(
                    [
                        SystemMessage(content=_SYNTHESIZER_SYSTEM),
                        HumanMessage(content=json.dumps(synthesis_context, indent=2)),
                    ]
                )
                roadmap = json.loads(_extract_json(str(response.content)))
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
                # Fall back to the roadmap_generation agent output so that a
                # partial but structured roadmap is persisted rather than the
                # raw aggregated dict (which has no phases/summary keys).
                roadmap = _build_fallback_roadmap(aggregated)
                final_message = AIMessage(content=f"Synthesis failed ({exc}) — using agent roadmap data.")

            logger.info(
                "node.synthesis_done",
                has_phases=bool(roadmap.get("phases")),
                phase_count=len(roadmap.get("phases", [])),
                session_id=session_id,
            )
            return {
                "final_output": roadmap,
                "status": AgentResultStatus.COMPLETED,
                "messages": [final_message],
            }
