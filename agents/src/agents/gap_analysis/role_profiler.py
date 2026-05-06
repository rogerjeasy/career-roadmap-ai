"""RoleProfiler — build a target role requirements profile via LLM.

Stateless component. Calls the LLM to enumerate required and preferred skills,
certifications, soft skills, portfolio project types, and ATS keywords for the
target role. Falls back to a minimal heuristic profile when the LLM fails.

Design: stateless, injectable LLM client, OTel + Prometheus observability.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import (
    GAP_ROLE_PROFILE_DURATION,
    GAP_ROLE_PROFILE_TOTAL,
    get_tracer,
)
from agents.gap_analysis.models import GapDimension, RoleProfile, RoleRequirement

logger = get_logger(__name__)
_tracer = get_tracer("agents.gap_analysis.role_profiler")

_SYSTEM_PROMPT = """\
You are a talent specialist who knows what skills, certifications, soft skills,
and portfolio projects are required for any given role. Return ONLY valid JSON (no fences):
{
  "typical_experience_months": <integer or null>,
  "requirements": [
    {
      "name": "<skill/cert/item name>",
      "dimension": "tech_skill|soft_skill|certification|portfolio|keyword",
      "is_required": true|false,
      "description": "<one-line description>",
      "typical_level": "beginner|intermediate|advanced|expert|null"
    }
  ],
  "keywords": ["<ATS keyword 1>", "<ATS keyword 2>", ...]
}

Guidelines:
- List 8-15 requirements: tech_skill (required & preferred), soft_skill (2-4),
  certification (if standard for the role), portfolio (2-3 project types).
- is_required=true for must-have items, false for nice-to-have.
- keywords: 5-10 ATS/resume keywords that should appear in a CV for this role.
- typical_experience_months: median months of experience required (null if it varies widely).
"""


class RoleProfiler:
    """Build a target role requirements profile.

    Inject a custom ``llm`` in tests to bypass real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def profile(
        self,
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> RoleProfile:
        """Return a RoleProfile for ``target_role``.

        Falls back to a minimal heuristic profile when all LLM retries fail.
        """
        with _tracer.start_as_current_span("gap.role_profile") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("target_role", target_role)
            t0 = time.monotonic()

            try:
                result = await self._profile_with_llm(target_role, correlation_id)
                GAP_ROLE_PROFILE_TOTAL.labels(status="llm").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "gap.role_profile_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    target_role=target_role,
                    correlation_id=correlation_id,
                )
                result = _heuristic_profile(target_role)
                GAP_ROLE_PROFILE_TOTAL.labels(status="fallback").inc()

            duration = time.monotonic() - t0
            GAP_ROLE_PROFILE_DURATION.observe(duration)
            span.set_attribute("requirement_count", len(result.requirements))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "gap.role_profiled",
                target_role=target_role,
                requirement_count=len(result.requirements),
                keyword_count=len(result.keywords),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _profile_with_llm(
        self, target_role: str, correlation_id: str
    ) -> RoleProfile:
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=f"Build the requirements profile for: {target_role}"),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return _build_role_profile(target_role, raw)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_role_profile(role_title: str, raw: dict[str, Any]) -> RoleProfile:
    requirements: list[RoleRequirement] = []
    for item in raw.get("requirements", []):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        dim_str = str(item.get("dimension", "tech_skill"))
        try:
            dimension = GapDimension(dim_str)
        except ValueError:
            dimension = GapDimension.TECH_SKILL
        requirements.append(
            RoleRequirement(
                name=str(item["name"]),
                dimension=dimension,
                is_required=bool(item.get("is_required", True)),
                description=str(item.get("description", "")),
                typical_level=item.get("typical_level") or None,
            )
        )
    keywords = [str(k) for k in raw.get("keywords", []) if k]
    exp_months = raw.get("typical_experience_months")
    if exp_months is not None:
        try:
            exp_months = int(exp_months)
        except (TypeError, ValueError):
            exp_months = None
    return RoleProfile(
        role_title=role_title,
        requirements=requirements,
        keywords=keywords,
        typical_experience_months=exp_months,
    )


def _heuristic_profile(role_title: str) -> RoleProfile:
    """Minimal fallback profile with generic software-engineering requirements."""
    requirements = [
        RoleRequirement(
            name="Problem Solving",
            dimension=GapDimension.SOFT_SKILL,
            is_required=True,
            description="Ability to decompose and solve complex problems",
        ),
        RoleRequirement(
            name="Communication",
            dimension=GapDimension.SOFT_SKILL,
            is_required=True,
            description="Clear written and verbal communication",
        ),
        RoleRequirement(
            name="Version Control (Git)",
            dimension=GapDimension.TECH_SKILL,
            is_required=True,
            typical_level="intermediate",
        ),
        RoleRequirement(
            name="Portfolio Project",
            dimension=GapDimension.PORTFOLIO,
            is_required=False,
            description="At least one relevant end-to-end project",
        ),
    ]
    return RoleProfile(
        role_title=role_title,
        requirements=requirements,
        keywords=[role_title],
        typical_experience_months=None,
    )
