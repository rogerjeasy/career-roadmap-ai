"""ValidatorAgent — L3 Specialist Agent: quality gate for generated career roadmaps.

Four-stage pipeline:
  Stage 1: EvidenceChecker  — evidence coverage for all roadmap claims
  Stage 2: ClaimAuditor     — hallucination detection (concurrent with Stage 3)
  Stage 3: RealismAssessor  — timeline + workload feasibility (concurrent with Stage 2)
  Stage 4: FixInstructor    — structured repair instructions

Input (via context.plan_snapshot):
  plan_snapshot["draft_roadmap"]       : dict  — generated roadmap from RoadmapAgent
  plan_snapshot["cv_analysis"]         : dict  — CV agent outputs
  plan_snapshot["gap_analysis"]        : dict  — gap analysis outputs
  plan_snapshot["market_intelligence"] : dict  — market intelligence outputs

Output (AgentResult.output — JSON-serialisable dict):
  passed                  : bool
  overall_score           : float   (0.0–1.0, weighted composite)
  evidence_coverage_score : float
  grounding_score         : float
  realism_score           : float
  evidence_checks         : list[dict]
  unsupported_claims      : list[dict]
  realism_issues          : list[dict]
  fix_instructions        : list[dict]
  evidence_check_status   : str     ("passed" | "degraded" | "failed")
  grounding_status        : str
  realism_status          : str
  processing_steps        : list[str]
  validation_duration_ms  : int

Pass thresholds:
  EVIDENCE_THRESHOLD  = 0.70
  GROUNDING_THRESHOLD = 0.65
  REALISM_THRESHOLD   = 0.60
  OVERALL_THRESHOLD   = 0.70
  A roadmap also fails if any FixInstruction has priority=CRITICAL.

Low-coupled: all four stages are injected via constructor DI and can be
             replaced independently for testing or extension.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each stage; Prometheus counters/histograms per stage.

Registration (at Celery worker startup):
    from agents.validator import ValidatorAgent
    from agents.core.agent_registry import registry
    registry.register(ValidatorAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    STEP_PROGRESS_TOTAL,
    VALIDATOR_PASSED_TOTAL,
    get_tracer,
)
from agents.validator.claim_auditor import ClaimAuditor
from agents.validator.evidence_checker import EvidenceChecker
from agents.validator.fix_instructor import FixInstructor
from agents.validator.models import (
    CheckStatus,
    FixPriority,
    ValidationResult,
)
from agents.validator.realism_assessor import RealismAssessor

logger = get_logger(__name__)
_tracer = get_tracer("agents.validator.validator_agent")

_EVIDENCE_THRESHOLD: float = 0.70
_GROUNDING_THRESHOLD: float = 0.65
_REALISM_THRESHOLD: float = 0.60
_OVERALL_THRESHOLD: float = 0.70

# Dimension weights for overall_score (must sum to 1.0)
_DIM_WEIGHTS: dict[str, float] = {
    "evidence": 0.35,
    "grounding": 0.40,
    "realism": 0.25,
}


class ValidatorAgent(BaseAgent):
    """Quality gate: validate and critique a generated career roadmap.

    Parameters
    ----------
    evidence_checker:
        Stage 1 evidence coverage checker.
    claim_auditor:
        Stage 2 hallucination detector.
    realism_assessor:
        Stage 3 timeline feasibility assessor.
    fix_instructor:
        Stage 4 repair instruction generator.
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events.
    llm:
        LLM override forwarded to all components that accept one.
    """

    def __init__(
        self,
        *,
        evidence_checker: EvidenceChecker | None = None,
        claim_auditor: ClaimAuditor | None = None,
        realism_assessor: RealismAssessor | None = None,
        fix_instructor: FixInstructor | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._evidence_checker = evidence_checker or EvidenceChecker(llm=llm)
        self._claim_auditor = claim_auditor or ClaimAuditor(llm=llm)
        self._realism_assessor = realism_assessor or RealismAssessor(llm=llm)
        self._fix_instructor = fix_instructor or FixInstructor(llm=llm)
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.VALIDATOR

    @property
    def display_name(self) -> str:
        return "Validator / Critic Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full validation pipeline and return a JSON-serialisable dict."""
        with _tracer.start_as_current_span("validator.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)
            t0 = time.monotonic()

            draft_roadmap: dict[str, Any] = context.plan_snapshot.get("draft_roadmap", {})
            agent_outputs: dict[str, Any] = {
                k: context.plan_snapshot.get(k, {})
                for k in ("cv_analysis", "gap_analysis", "market_intelligence")
            }
            user_profile_dict = _extract_user_profile(context)

            if not draft_roadmap:
                logger.warning(
                    "validator.no_draft_roadmap",
                    session_id=context.session_id,
                    correlation_id=context.correlation_id,
                )
                result = _empty_result(t0)
                VALIDATOR_PASSED_TOTAL.labels(result="failed").inc()
                span.set_attribute("passed", False)
                span.set_attribute("reason", "no_draft_roadmap")
                span.set_status(Status(StatusCode.OK))
                return result.to_dict()

            # ── Stage 1: Evidence Coverage ─────────────────────────────────
            self._emit_progress(
                context, "evidence_coverage", "Checking evidence coverage…"
            )
            STEP_PROGRESS_TOTAL.labels(step_name="validator.evidence_coverage").inc()

            evidence_checks, evidence_score = await self._evidence_checker.check(
                agent_outputs,
                draft_roadmap,
                correlation_id=context.correlation_id,
            )

            # ── Stages 2 + 3: Concurrent ───────────────────────────────────
            self._emit_progress(
                context,
                "claim_audit_and_realism",
                "Auditing claims and assessing timeline realism…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="validator.claim_audit").inc()
            STEP_PROGRESS_TOTAL.labels(step_name="validator.realism_assess").inc()

            (unsupported_claims, grounding_score), (realism_issues, realism_score) = (
                await asyncio.gather(
                    self._claim_auditor.audit(
                        agent_outputs,
                        draft_roadmap,
                        correlation_id=context.correlation_id,
                    ),
                    self._realism_assessor.assess(
                        draft_roadmap,
                        user_profile_dict,
                        correlation_id=context.correlation_id,
                    ),
                )
            )

            # ── Stage 4: Fix Instructions ──────────────────────────────────
            self._emit_progress(
                context, "fix_instructions", "Generating repair instructions…"
            )
            STEP_PROGRESS_TOTAL.labels(step_name="validator.fix_instructions").inc()

            fix_instructions = await self._fix_instructor.generate(
                evidence_checks,
                unsupported_claims,
                realism_issues,
                correlation_id=context.correlation_id,
            )

            # ── Aggregate ──────────────────────────────────────────────────
            overall_score = round(
                evidence_score * _DIM_WEIGHTS["evidence"]
                + grounding_score * _DIM_WEIGHTS["grounding"]
                + realism_score * _DIM_WEIGHTS["realism"],
                3,
            )
            has_critical = any(
                f.priority == FixPriority.CRITICAL for f in fix_instructions
            )
            passed = (
                evidence_score >= _EVIDENCE_THRESHOLD
                and grounding_score >= _GROUNDING_THRESHOLD
                and realism_score >= _REALISM_THRESHOLD
                and overall_score >= _OVERALL_THRESHOLD
                and not has_critical
            )

            result = ValidationResult(
                passed=passed,
                overall_score=overall_score,
                evidence_coverage_score=evidence_score,
                grounding_score=grounding_score,
                realism_score=realism_score,
                evidence_checks=evidence_checks,
                unsupported_claims=unsupported_claims,
                realism_issues=realism_issues,
                fix_instructions=fix_instructions,
                evidence_check_status=_score_to_status(evidence_score, _EVIDENCE_THRESHOLD),
                grounding_status=_score_to_status(grounding_score, _GROUNDING_THRESHOLD),
                realism_status=_score_to_status(realism_score, _REALISM_THRESHOLD),
                processing_steps=[
                    "evidence_coverage",
                    "claim_audit",
                    "realism_assess",
                    "fix_instructions",
                ],
                validation_duration_ms=int((time.monotonic() - t0) * 1000),
            )

            outcome = "passed" if passed else "failed"
            VALIDATOR_PASSED_TOTAL.labels(result=outcome).inc()
            span.set_attribute("passed", passed)
            span.set_attribute("overall_score", overall_score)
            span.set_attribute("evidence_score", evidence_score)
            span.set_attribute("grounding_score", grounding_score)
            span.set_attribute("realism_score", realism_score)
            span.set_attribute("fix_count", len(fix_instructions))
            span.set_attribute("critical_fixes", int(has_critical))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "validator.completed",
                passed=passed,
                overall_score=overall_score,
                evidence_score=evidence_score,
                grounding_score=grounding_score,
                realism_score=realism_score,
                fix_count=len(fix_instructions),
                critical_fixes=has_critical,
                duration_ms=result.validation_duration_ms,
                session_id=context.session_id,
                correlation_id=context.correlation_id,
            )
            return result.to_dict()

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(
        self, context: AgentContext, step: str, description: str
    ) -> None:
        """Best-effort STEP_PROGRESS event emission. Never raises."""
        if self._event_publisher is None:
            return
        try:
            self._event_publisher.emit(
                AgentEvent(
                    event_type=AgentEventType.STEP_PROGRESS,
                    session_id=context.session_id,
                    user_id=context.user_id,
                    correlation_id=context.correlation_id,
                    payload={
                        "agent": self.agent_type.value,
                        "step": step,
                        "description": description,
                    },
                )
            )
        except Exception as exc:
            logger.warning(
                "validator.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Module-level helpers ───────────────────────────────────────────────────────


def _extract_user_profile(context: AgentContext) -> dict[str, Any]:
    """Produce a plain dict from AgentContext.user_profile for stage inputs."""
    return {
        "target_role": context.user_profile.target_role,
        "current_role": context.user_profile.current_role,
        "skills": list(context.user_profile.skills),
        "timeline_months": context.user_profile.timeline_months,
        "weekly_hours_available": context.user_profile.weekly_hours_available,
        "constraints": list(context.user_profile.constraints),
    }


def _score_to_status(score: float, threshold: float) -> CheckStatus:
    if score >= threshold:
        return CheckStatus.PASSED
    if score >= threshold * 0.75:
        return CheckStatus.DEGRADED
    return CheckStatus.FAILED


def _empty_result(t0: float) -> ValidationResult:
    return ValidationResult(
        passed=False,
        overall_score=0.0,
        evidence_coverage_score=0.0,
        grounding_score=0.0,
        realism_score=0.0,
        evidence_check_status=CheckStatus.FAILED,
        grounding_status=CheckStatus.FAILED,
        realism_status=CheckStatus.FAILED,
        processing_steps=[],
        validation_duration_ms=int((time.monotonic() - t0) * 1000),
    )
