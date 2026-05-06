"""OutputValidator — three-stage validation of synthesised career roadmaps.

Pipeline:
  Stage 1 — Realism + Coherence   (LLM, temp=0, sequential)
             Gate: if both checks fail, skip Stages 2+3 immediately.
  Stage 2 — Grounding check       (LLM, temp=0, concurrent with Stage 3)
             Detects hallucinations: claims not backed by agent outputs.
  Stage 3 — Per-step confidence   (LLM, temp=0, concurrent with Stage 2)
             Scores each roadmap phase 0.0–1.0 for achievability.

All three stages use tenacity retries (3 attempts, exponential backoff).
Each stage opens its own OTel span and records to Prometheus.

Design:
- Stateless: all inputs passed as arguments; no instance state mutated.
- Decoupled: depends only on agents.contracts, agents.config, agents.core.
- Graceful: any single-stage failure degrades the report, not the pipeline.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agents.config import agent_settings
from agents.contracts.results import AgentResult, AgentResultStatus
from agents.core.logging import get_logger
from agents.core.observability import (
    VALIDATION_GROUNDING_SCORE,
    VALIDATION_PASSED_TOTAL,
    VALIDATION_STAGE_DURATION,
    get_tracer,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.output_validator")

# Grounding score must meet or exceed this to count toward ``passed``.
_GROUNDING_THRESHOLD: float = 0.5

# ── System prompts ─────────────────────────────────────────────────────────

_STAGE1_SYSTEM = """\
You are a quality-control reviewer for AI-generated career roadmaps.
You will receive a JSON roadmap. Assess two dimensions independently:

1. REALISM — Is the timeline plausible given the skill complexity?
   Flag if any phase requires mastery of a fundamentally new discipline in
   fewer than 4 weeks, or if the total duration is shorter than the
   cumulative skill acquisition time.

2. COHERENCE — Do the roadmap phases follow a logical skill-building order?
   Are prerequisites established before advanced topics appear?

Reply with ONLY a JSON object — no prose, no markdown:
{
  "realism_passed": true|false,
  "coherence_passed": true|false,
  "notes": ["note1", "note2"]
}
Limit notes to 3 specific, actionable items. Return [] if nothing to flag.
"""

_STAGE2_SYSTEM = """\
You are a factual grounding auditor for AI-generated career roadmaps.
You will receive:
  A) agent_data — raw outputs from specialist AI agents (ground truth)
  B) roadmap    — the synthesised roadmap

Your task: for every concrete claim in the roadmap (skills to gain, tools to
learn, salary ranges, market demand statements, specific resource names,
timeline estimates) determine whether it is directly supported by agent_data.

A claim is GROUNDED if the concept appears in at least one agent output.
A claim is UNVERIFIED if it was introduced by the synthesiser with no source.

Reply with ONLY a JSON object — no prose, no markdown:
{
  "grounding_score": 0.0,
  "unverified_claims": ["verbatim claim 1", "verbatim claim 2"]
}
grounding_score = verified_count / total_count, rounded to 2 decimal places.
Return "unverified_claims": [] if all claims are grounded.
"""

_STAGE3_SYSTEM = """\
You are a career coaching expert evaluating the achievability of each phase
in an AI-generated career roadmap.

For each phase in the "phases" array, score confidence (0.0–1.0) that a
motivated learner can complete it as described. Consider:
  - Plausibility of the milestone list within duration_weeks
  - Specificity of skills_to_gain (vague skills → lower confidence)
  - Logical dependency on the preceding phase

Score guide:
  1.0 = highly specific, realistic timeline, well-sequenced
  0.7 = mostly concrete, minor concerns
  0.5 = generic or duration uncertain
  0.3 = ambitious but possibly achievable
  0.0 = implausible or critical information missing

Reply with ONLY a JSON array — one object per phase, same order as input:
[
  {
    "phase_index": 0,
    "phase_title": "exact title from the roadmap",
    "confidence": 0.0,
    "reasoning": "one sentence"
  }
]
"""


# ── Data types ─────────────────────────────────────────────────────────────


@dataclass
class StepConfidence:
    """Confidence assessment for one roadmap phase."""

    phase_index: int
    phase_title: str
    confidence: float  # 0.0–1.0
    reasoning: str     # ≤ 1 sentence explanation


@dataclass
class ValidationReport:
    """Full structured output from ``OutputValidator.validate()``.

    Call ``to_dict()`` before writing into OrchestratorState so the value
    is JSON-serialisable (plain dicts, no dataclass instances).
    """

    # Stage 1
    realism_passed: bool
    coherence_passed: bool
    stage1_notes: list[str]

    # Stage 2
    grounding_score: float
    unverified_claims: list[str]

    # Stage 3
    step_confidences: list[StepConfidence]
    mean_step_confidence: float

    # Aggregate
    passed: bool
    notes: list[str]
    validation_duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serialisable dict for OrchestratorState storage."""
        return asdict(self)


# ── Validator ──────────────────────────────────────────────────────────────


class OutputValidator:
    """Three-stage validator for synthesised career roadmaps.

    One instance per MasterOrchestrator; all validation methods are stateless.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.validator_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=1024,
            temperature=0.0,
        )

    async def validate(
        self,
        agent_results: dict[str, AgentResult],
        roadmap: dict[str, Any],
        *,
        session_id: str = "",
        correlation_id: str = "",
    ) -> ValidationReport:
        """Run all three validation stages and return a ``ValidationReport``.

        Stages 2 and 3 run concurrently after Stage 1 completes.
        If Stage 1 fails both checks the expensive LLM calls are skipped.
        """
        with _tracer.start_as_current_span("output_validator.validate") as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            # ── Stage 1: Realism + Coherence ──────────────────────────────
            realism_passed, coherence_passed, stage1_notes = (
                await self._stage1_realism(roadmap, correlation_id=correlation_id)
            )

            # Gate: skip Stages 2+3 if the roadmap is clearly unusable.
            if not realism_passed and not coherence_passed:
                report = _failed_report(stage1_notes, t0)
                _record_outcome(report, span)
                logger.warning(
                    "output_validator.early_exit",
                    reason="realism_and_coherence_both_failed",
                    session_id=session_id,
                    correlation_id=correlation_id,
                )
                return report

            # ── Stages 2 + 3: concurrent ──────────────────────────────────
            agent_data = {
                k: v.output
                for k, v in agent_results.items()
                if v.status == AgentResultStatus.COMPLETED
            }

            (grounding_score, unverified_claims), step_confidences = await asyncio.gather(
                self._stage2_grounding(agent_data, roadmap, correlation_id=correlation_id),
                self._stage3_step_confidence(roadmap, correlation_id=correlation_id),
            )

            mean_conf = (
                round(
                    sum(s.confidence for s in step_confidences) / len(step_confidences),
                    3,
                )
                if step_confidences
                else 0.0
            )

            passed = (
                realism_passed
                and coherence_passed
                and grounding_score >= _GROUNDING_THRESHOLD
            )

            notes: list[str] = list(stage1_notes)
            if grounding_score < _GROUNDING_THRESHOLD:
                notes.append(
                    f"Grounding score {grounding_score:.2f} is below the "
                    f"{_GROUNDING_THRESHOLD:.2f} threshold."
                )
            if unverified_claims:
                notes.append(
                    f"{len(unverified_claims)} unverified claim(s) flagged."
                )

            report = ValidationReport(
                realism_passed=realism_passed,
                coherence_passed=coherence_passed,
                stage1_notes=stage1_notes,
                grounding_score=grounding_score,
                unverified_claims=unverified_claims,
                step_confidences=step_confidences,
                mean_step_confidence=mean_conf,
                passed=passed,
                notes=notes,
                validation_duration_ms=int((time.monotonic() - t0) * 1000),
            )
            _record_outcome(report, span)

            logger.info(
                "output_validator.done",
                passed=passed,
                grounding_score=grounding_score,
                mean_step_confidence=mean_conf,
                unverified_count=len(unverified_claims),
                duration_ms=report.validation_duration_ms,
                session_id=session_id,
                correlation_id=correlation_id,
            )
            return report

    # ── Stage 1 ───────────────────────────────────────────────────────────

    async def _stage1_realism(
        self,
        roadmap: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[bool, bool, list[str]]:
        with _tracer.start_as_current_span("output_validator.stage1") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_stage1(roadmap)
                realism: bool = bool(raw.get("realism_passed", True))
                coherence: bool = bool(raw.get("coherence_passed", True))
                notes: list[str] = raw.get("notes", [])[:3]
                span.set_attribute("realism_passed", realism)
                span.set_attribute("coherence_passed", coherence)
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "output_validator.stage1_fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                realism, coherence, notes = True, True, []
            finally:
                VALIDATION_STAGE_DURATION.labels(stage="realism_coherence").observe(
                    time.monotonic() - t0
                )
            return realism, coherence, notes

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_stage1(self, roadmap: dict[str, Any]) -> dict[str, Any]:
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_STAGE1_SYSTEM),
                HumanMessage(content=f"Roadmap:\n{json.dumps(roadmap, indent=2)}"),
            ]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Stage 1 expected dict, got {type(result).__name__}")
        return result

    # ── Stage 2 ───────────────────────────────────────────────────────────

    async def _stage2_grounding(
        self,
        agent_data: dict[str, Any],
        roadmap: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[float, list[str]]:
        with _tracer.start_as_current_span("output_validator.stage2") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_stage2(agent_data, roadmap)
                score = max(0.0, min(1.0, float(raw.get("grounding_score", 1.0))))
                claims: list[str] = raw.get("unverified_claims", [])
                VALIDATION_GROUNDING_SCORE.observe(score)
                span.set_attribute("grounding_score", score)
                span.set_attribute("unverified_count", len(claims))
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "output_validator.stage2_fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                score, claims = 1.0, []
            finally:
                VALIDATION_STAGE_DURATION.labels(stage="grounding").observe(
                    time.monotonic() - t0
                )
            return score, claims

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_stage2(
        self, agent_data: dict[str, Any], roadmap: dict[str, Any]
    ) -> dict[str, Any]:
        content = json.dumps({"agent_data": agent_data, "roadmap": roadmap}, indent=2)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_STAGE2_SYSTEM),
                HumanMessage(content=content),
            ]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Stage 2 expected dict, got {type(result).__name__}")
        return result

    # ── Stage 3 ───────────────────────────────────────────────────────────

    async def _stage3_step_confidence(
        self,
        roadmap: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> list[StepConfidence]:
        phases = roadmap.get("phases", [])
        if not phases:
            return []

        with _tracer.start_as_current_span("output_validator.stage3") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_stage3(roadmap)
                result = [
                    StepConfidence(
                        phase_index=int(item.get("phase_index", i)),
                        phase_title=str(item.get("phase_title", f"Phase {i + 1}")),
                        confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                        reasoning=str(item.get("reasoning", "")),
                    )
                    for i, item in enumerate(raw)
                ]
                span.set_attribute("phases_scored", len(result))
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "output_validator.stage3_fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                result = [
                    StepConfidence(
                        phase_index=i,
                        phase_title=p.get("title", f"Phase {i + 1}"),
                        confidence=0.5,
                        reasoning="Confidence scoring unavailable.",
                    )
                    for i, p in enumerate(phases)
                ]
            finally:
                VALIDATION_STAGE_DURATION.labels(stage="confidence").observe(
                    time.monotonic() - t0
                )
            return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_stage3(self, roadmap: dict[str, Any]) -> list[dict[str, Any]]:
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_STAGE3_SYSTEM),
                HumanMessage(content=f"Roadmap:\n{json.dumps(roadmap, indent=2)}"),
            ]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, list):
            raise ValueError(f"Stage 3 expected list, got {type(result).__name__}")
        return result


# ── Factories & helpers ────────────────────────────────────────────────────


def make_output_validator(llm: ChatAnthropic | None = None) -> OutputValidator:
    """Factory used by MasterOrchestrator and the LangGraph node."""
    return OutputValidator(llm)


def _failed_report(stage1_notes: list[str], t0: float) -> ValidationReport:
    return ValidationReport(
        realism_passed=False,
        coherence_passed=False,
        stage1_notes=stage1_notes,
        grounding_score=0.0,
        unverified_claims=[],
        step_confidences=[],
        mean_step_confidence=0.0,
        passed=False,
        notes=stage1_notes,
        validation_duration_ms=int((time.monotonic() - t0) * 1000),
    )


def _record_outcome(report: ValidationReport, span: Any) -> None:
    label = "passed" if report.passed else "failed"
    VALIDATION_PASSED_TOTAL.labels(result=label).inc()
    span.set_attribute("passed", report.passed)
    span.set_attribute("grounding_score", report.grounding_score)
    span.set_attribute("mean_step_confidence", report.mean_step_confidence)
    span.set_attribute("unverified_claims_count", len(report.unverified_claims))
    span.set_attribute("duration_ms", report.validation_duration_ms)
    span.set_status(Status(StatusCode.OK))
