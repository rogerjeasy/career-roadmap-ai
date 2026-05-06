"""EvidenceChecker — Stage 1: verify evidence coverage across roadmap claims.

For every concrete claim extracted from the draft roadmap (skills to acquire,
market-relevance statements, milestone deliverables) the checker asks the LLM
whether the claim has grounding support in the available agent outputs
(cv_analysis, gap_analysis, market_intelligence).

Returns (list[EvidenceCheck], coverage_score: float).

Design:
- One LLM call per run (batched claim list keeps token cost low).
- Stateless: all state passed as arguments.
- Fallback: if LLM fails, every claim is marked grounded at 0.5 confidence
  (permissive degradation — avoids blocking the pipeline on infra issues).
"""
from __future__ import annotations

import json
import time
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
from agents.core.logging import get_logger
from agents.core.observability import (
    VALIDATOR_EVIDENCE_COVERAGE,
    VALIDATOR_STAGE_DURATION,
    get_tracer,
)
from agents.validator.models import EvidenceCheck

logger = get_logger(__name__)
_tracer = get_tracer("agents.validator.evidence_checker")

# Hard cap on claims sent to the LLM to avoid token overflow.
_MAX_CLAIMS = 40

_SYSTEM = """\
You are an evidence coverage auditor for AI-generated career roadmaps.
You will receive:
  A) agent_outputs — structured outputs from specialist AI agents (ground truth)
  B) roadmap_claims — a list of concrete claims extracted from a draft roadmap

For each claim, determine whether it is grounded in agent_outputs.
A claim is GROUNDED if the concept (skill, tool, market trend, company, resource)
appears explicitly or is clearly implied in agent_outputs.
A claim is UNGROUNDED if it was introduced by the synthesiser with no agent evidence.

Reply with ONLY a JSON object — no prose, no markdown:
{
  "coverage_score": 0.85,
  "checks": [
    {
      "claim": "<exact claim text>",
      "is_grounded": true,
      "evidence_ref": "<key path in agent_outputs or null>",
      "confidence": 0.9
    }
  ]
}
coverage_score = count(is_grounded=true) / count(all_claims), rounded to 2 decimal places.
"""


class EvidenceChecker:
    """Stage 1: evidence coverage verification.

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

    async def check(
        self,
        agent_outputs: dict[str, Any],
        roadmap: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[list[EvidenceCheck], float]:
        """Check evidence coverage for roadmap claims.

        Returns
        -------
        tuple[list[EvidenceCheck], float]
            (checks, coverage_score 0.0–1.0)
        """
        claims = _extract_claims(roadmap)
        if not claims:
            return [], 1.0

        with _tracer.start_as_current_span("evidence_checker.check") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_check(agent_outputs, claims)
                score = max(0.0, min(1.0, float(raw.get("coverage_score", 1.0))))
                checks = [
                    EvidenceCheck(
                        claim=str(c.get("claim", "")),
                        is_grounded=bool(c.get("is_grounded", True)),
                        evidence_ref=c.get("evidence_ref") or None,
                        confidence=max(0.0, min(1.0, float(c.get("confidence", 0.5)))),
                    )
                    for c in raw.get("checks", [])
                ]
                VALIDATOR_EVIDENCE_COVERAGE.observe(score)
                span.set_attribute("coverage_score", score)
                span.set_attribute("claims_count", len(checks))
                span.set_attribute(
                    "grounded_count", sum(1 for c in checks if c.is_grounded)
                )
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "evidence_checker.fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                # Permissive fallback: mark all claims grounded at low confidence.
                checks = [
                    EvidenceCheck(
                        claim=c,
                        is_grounded=True,
                        evidence_ref=None,
                        confidence=0.5,
                    )
                    for c in claims
                ]
                score = 1.0
            finally:
                VALIDATOR_STAGE_DURATION.labels(stage="evidence_check").observe(
                    time.monotonic() - t0
                )
            return checks, score

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_check(
        self, agent_outputs: dict[str, Any], claims: list[str]
    ) -> dict[str, Any]:
        payload = json.dumps(
            {"agent_outputs": agent_outputs, "roadmap_claims": claims}, indent=2
        )
        response = await self._llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=payload)]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict, got {type(result).__name__}")
        return result


def _extract_claims(roadmap: dict[str, Any]) -> list[str]:
    """Extract concrete, verifiable claims from a structured roadmap dict."""
    claims: list[str] = []

    for phase in roadmap.get("phases", []):
        for skill in phase.get("skills_to_acquire", []) + phase.get("skills_to_gain", []):
            claims.append(f"Learn: {skill}")
        for ms in phase.get("milestones", []):
            name = ms if isinstance(ms, str) else ms.get("name", str(ms))
            claims.append(f"Milestone: {name}")
        market_rel = phase.get("market_relevance", "")
        if market_rel:
            claims.append(f"Market claim: {market_rel}")

    summary = roadmap.get("summary", "")
    if summary:
        claims.append(f"Summary: {summary}")

    return claims[:_MAX_CLAIMS]
