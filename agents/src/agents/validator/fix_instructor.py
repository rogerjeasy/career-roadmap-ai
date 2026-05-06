"""FixInstructor — Stage 4: generate structured repair instructions.

Consumes all issues found in Stages 1–3 and produces a ranked, de-duplicated
list of FixInstruction objects that the Roadmap Synthesis Agent can use to
repair the draft roadmap in a targeted, verifiable way.

Returns list[FixInstruction] (empty list if no issues were found).

Design:
- One LLM call to synthesise all issues into coherent, non-redundant instructions.
- Stateless: all state passed as arguments.
- Fallback: if LLM fails, deterministic fallback instructions are generated from
  the raw issue lists so the pipeline always produces actionable output.
"""
from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

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
from agents.core.logging import get_logger
from agents.core.observability import (
    VALIDATOR_FIX_COUNT,
    VALIDATOR_FIX_INSTRUCTIONS_TOTAL,
    VALIDATOR_STAGE_DURATION,
    get_tracer,
)
from agents.validator.models import (
    EvidenceCheck,
    FixInstruction,
    FixPriority,
    RealismIssue,
    UnsupportedClaim,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.validator.fix_instructor")

_SYSTEM = """\
You are a senior career roadmap editor. You will receive a list of validation
issues found in a draft career roadmap:
  - evidence_gaps:      claims with no evidence backing (from EvidenceChecker)
  - unsupported_claims: hallucinated or invented claims (from ClaimAuditor)
  - realism_issues:     timeline or workload infeasibility (from RealismAssessor)

Your task: produce a concise, ranked list of FixInstructions for the Roadmap
Synthesis Agent to repair the draft. Each instruction must be:
  1. Specific: identify the exact location in the roadmap
  2. Actionable: tell the agent precisely what to change or replace
  3. Non-redundant: merge related issues into a single instruction when possible

Priority:
  critical — must fix before the roadmap can be shown to the user
  high     — should fix; significantly degrades quality if left
  low      — optional improvement; cosmetic or speculative

Reply with ONLY a JSON array — no prose, no markdown:
[
  {
    "issue_id": "fix_001",
    "priority": "critical",
    "category": "unsupported_claim",
    "description": "concise issue description",
    "suggested_action": "specific, targeted action for the roadmap agent",
    "roadmap_location": "phases[1].market_relevance"
  }
]
Return [] if no fixes are needed.
"""


class FixInstructor:
    """Stage 4: generate structured repair instructions from all validation issues.

    Parameters
    ----------
    llm:
        Override the default LLM instance (primarily for testing).
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.validator_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def generate(
        self,
        evidence_checks: list[EvidenceCheck],
        unsupported_claims: list[UnsupportedClaim],
        realism_issues: list[RealismIssue],
        *,
        correlation_id: str = "",
    ) -> list[FixInstruction]:
        """Generate structured repair instructions from all validation issues.

        Returns
        -------
        list[FixInstruction]
            Empty list if no issues were found.
        """
        gaps = [c for c in evidence_checks if not c.is_grounded]
        if not gaps and not unsupported_claims and not realism_issues:
            return []

        with _tracer.start_as_current_span("fix_instructor.generate") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_generate(gaps, unsupported_claims, realism_issues)
                instructions = [
                    FixInstruction(
                        issue_id=str(item.get("issue_id", f"fix_{i:03d}")),
                        priority=_parse_priority(item.get("priority", "low")),
                        category=str(item.get("category", "general")),
                        description=str(item.get("description", "")),
                        suggested_action=str(item.get("suggested_action", "")),
                        roadmap_location=str(item.get("roadmap_location", "unknown")),
                    )
                    for i, item in enumerate(raw)
                ]
                _record_metrics(instructions)
                span.set_attribute("fix_count", len(instructions))
                span.set_attribute(
                    "critical_count",
                    sum(1 for f in instructions if f.priority == FixPriority.CRITICAL),
                )
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "fix_instructor.fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                instructions = _fallback_instructions(gaps, unsupported_claims, realism_issues)
                _record_metrics(instructions)
            finally:
                VALIDATOR_STAGE_DURATION.labels(stage="fix_instructions").observe(
                    time.monotonic() - t0
                )
            return instructions

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_generate(
        self,
        gaps: list[EvidenceCheck],
        unsupported_claims: list[UnsupportedClaim],
        realism_issues: list[RealismIssue],
    ) -> list[dict[str, Any]]:
        payload = json.dumps(
            {
                "evidence_gaps": [
                    {"claim": c.claim, "confidence": c.confidence}
                    for c in gaps
                ],
                "unsupported_claims": [
                    {
                        "claim": c.claim,
                        "location": c.roadmap_location,
                        "severity": c.severity.value,
                    }
                    for c in unsupported_claims
                ],
                "realism_issues": [
                    {
                        "description": r.description,
                        "phase_index": r.phase_index,
                        "severity": r.severity.value,
                        "suggested_adjustment": r.suggested_adjustment,
                    }
                    for r in realism_issues
                ],
            },
            indent=2,
        )
        response = await self._llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=payload)]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, list):
            raise ValueError(f"Expected list, got {type(result).__name__}")
        return result


# ── Helpers ────────────────────────────────────────────────────────────────────


def _record_metrics(instructions: list[FixInstruction]) -> None:
    VALIDATOR_FIX_COUNT.observe(len(instructions))
    for fix in instructions:
        VALIDATOR_FIX_INSTRUCTIONS_TOTAL.labels(priority=fix.priority.value).inc()


def _parse_priority(value: str) -> FixPriority:
    try:
        return FixPriority(value.lower())
    except ValueError:
        return FixPriority.LOW


def _fallback_instructions(
    gaps: list[EvidenceCheck],
    claims: list[UnsupportedClaim],
    realism: list[RealismIssue],
) -> list[FixInstruction]:
    """Deterministic fallback instructions when the LLM is unavailable."""
    instructions: list[FixInstruction] = []

    if gaps:
        instructions.append(
            FixInstruction(
                issue_id=_short_id(),
                priority=FixPriority.HIGH,
                category="evidence_gap",
                description=f"{len(gaps)} roadmap claim(s) lack evidence backing.",
                suggested_action=(
                    "Review each ungrounded claim and either remove it or replace it "
                    "with a statement backed by cv_analysis, gap_analysis, or "
                    "market_intelligence outputs."
                ),
                roadmap_location="multiple",
            )
        )

    if claims:
        critical = any(c.severity == FixPriority.CRITICAL for c in claims)
        instructions.append(
            FixInstruction(
                issue_id=_short_id(),
                priority=FixPriority.CRITICAL if critical else FixPriority.HIGH,
                category="unsupported_claim",
                description=f"{len(claims)} unsupported claim(s) detected.",
                suggested_action=(
                    "Remove or replace each unsupported claim with agent-backed evidence. "
                    "Do not invent salary ranges, market demand, or tool adoption figures."
                ),
                roadmap_location="multiple",
            )
        )

    for issue in realism[:3]:  # cap to avoid flooding the repair agent
        instructions.append(
            FixInstruction(
                issue_id=_short_id(),
                priority=issue.severity,
                category="timeline",
                description=issue.description,
                suggested_action=issue.suggested_adjustment,
                roadmap_location=(
                    f"phases[{issue.phase_index}]"
                    if issue.phase_index is not None
                    else "roadmap"
                ),
            )
        )

    return instructions


def _short_id() -> str:
    return str(uuid4())[:8]
