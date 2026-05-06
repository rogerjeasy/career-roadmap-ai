"""ClaimAuditor — Stage 2: detect unsupported claims (hallucination detection).

For every concrete claim in the roadmap that is NOT backed by any agent output,
the auditor flags it as unsupported, assigns a severity, and records the
location within the roadmap structure.

Returns (list[UnsupportedClaim], grounding_score: float).

Design:
- One LLM call per run (full roadmap vs all agent data).
- Stateless: all state passed as arguments.
- Fallback: if LLM fails, no claims are flagged and score=1.0 (permissive —
  avoids false positives that would incorrectly block a good roadmap).
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
    VALIDATOR_GROUNDING_SCORE,
    VALIDATOR_STAGE_DURATION,
    VALIDATOR_UNSUPPORTED_CLAIMS_TOTAL,
    get_tracer,
)
from agents.validator.models import FixPriority, UnsupportedClaim

logger = get_logger(__name__)
_tracer = get_tracer("agents.validator.claim_auditor")

_SYSTEM = """\
You are a factual grounding auditor for AI-generated career roadmaps.
You will receive:
  A) agent_data — raw outputs from specialist AI agents (ground truth)
  B) roadmap    — the synthesised career roadmap

Your task: identify every concrete claim in the roadmap that is NOT backed by
agent_data. Claims that introduce salary figures, timeline estimates, specific
tool names, company names, trending skills, or market demand statements without
corresponding agent evidence are UNSUPPORTED.

Severity guide:
  critical — claim could mislead the user into a harmful decision
             (e.g. fabricated salary range, fake certification value)
  high     — claim is likely incorrect and would degrade roadmap quality
  low      — claim is speculative or vague but not immediately harmful

Reply with ONLY a JSON object — no prose, no markdown:
{
  "grounding_score": 0.87,
  "unsupported_claims": [
    {
      "claim": "verbatim claim text",
      "roadmap_location": "phases[1].market_relevance",
      "severity": "high"
    }
  ]
}
grounding_score = verified_count / total_count, rounded to 2 decimal places.
Return "unsupported_claims": [] if all claims are grounded.
"""


class ClaimAuditor:
    """Stage 2: detect hallucinated or unsupported claims in the roadmap.

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

    async def audit(
        self,
        agent_data: dict[str, Any],
        roadmap: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[list[UnsupportedClaim], float]:
        """Audit the roadmap for unsupported claims.

        Returns
        -------
        tuple[list[UnsupportedClaim], float]
            (unsupported_claims, grounding_score 0.0–1.0)
        """
        with _tracer.start_as_current_span("claim_auditor.audit") as span:
            t0 = time.monotonic()
            try:
                raw = await self._llm_audit(agent_data, roadmap)
                score = max(0.0, min(1.0, float(raw.get("grounding_score", 1.0))))
                claims = [
                    UnsupportedClaim(
                        claim=str(c.get("claim", "")),
                        roadmap_location=str(c.get("roadmap_location", "unknown")),
                        severity=_parse_priority(c.get("severity", "low")),
                    )
                    for c in raw.get("unsupported_claims", [])
                ]
                VALIDATOR_GROUNDING_SCORE.observe(score)
                if claims:
                    VALIDATOR_UNSUPPORTED_CLAIMS_TOTAL.inc(len(claims))
                span.set_attribute("grounding_score", score)
                span.set_attribute("unsupported_count", len(claims))
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "claim_auditor.fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                # Permissive fallback: no false positives, assume grounded.
                claims, score = [], 1.0
            finally:
                VALIDATOR_STAGE_DURATION.labels(stage="claim_audit").observe(
                    time.monotonic() - t0
                )
            return claims, score

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_audit(
        self, agent_data: dict[str, Any], roadmap: dict[str, Any]
    ) -> dict[str, Any]:
        content = json.dumps(
            {"agent_data": agent_data, "roadmap": roadmap}, indent=2
        )
        response = await self._llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=content)]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict, got {type(result).__name__}")
        return result


def _parse_priority(value: str) -> FixPriority:
    try:
        return FixPriority(value.lower())
    except ValueError:
        return FixPriority.LOW
