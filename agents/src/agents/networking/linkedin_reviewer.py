"""LinkedInReviewer — score a LinkedIn profile and provide targeted improvement advice.

Takes raw profile data (from MCP or CV) and target role, then uses an LLM to:
  - Score headline, summary, experience, skills, and ATS match (0-1 each)
  - Identify specific strengths
  - Generate concrete, actionable improvements
  - Recommend ATS keywords for the target role

Falls back to a heuristic score when all LLM retries fail so the pipeline
never crashes due to LLM unavailability.
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
    NET_LINKEDIN_REVIEW_DURATION,
    NET_LINKEDIN_REVIEW_TOTAL,
    get_tracer,
)
from agents.networking.models import LinkedInProfileScore

logger = get_logger(__name__)
_tracer = get_tracer("agents.networking.linkedin_reviewer")

_SYSTEM_PROMPT = """\
You are a LinkedIn optimization expert and senior career coach. You review LinkedIn profiles
and provide precise, actionable feedback for job seekers targeting a specific role.

Analyze the provided profile data and target role, then return ONLY valid JSON (no fences):
{
  "headline_score": <float 0.0-1.0>,
  "summary_score": <float 0.0-1.0>,
  "experience_score": <float 0.0-1.0>,
  "skills_score": <float 0.0-1.0>,
  "overall_score": <float 0.0-1.0>,
  "ats_score": <float 0.0-1.0>,
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<specific actionable improvement 1>", "<improvement 2>"],
  "recommended_keywords": ["<keyword 1>", "<keyword 2>"]
}

Scoring guidelines:
  headline_score  — Is it role-specific, keyword-rich, and compelling? (0.9+ = excellent)
  summary_score   — Does it tell a story, include accomplishments, target the desired role?
  experience_score — Are achievements quantified? Are descriptions impact-focused?
  skills_score    — Are target-role skills listed? Is the section complete and prioritised?
  ats_score       — Would an ATS rank this profile well for the target role?
  overall_score   — Weighted average: headline 20%, summary 25%, experience 30%, skills 15%, other 10%

Content guidelines:
  strengths    — 2-4 specific positive observations (not generic praise)
  improvements — 3-6 concrete, actionable changes the user can make today
  recommended_keywords — 5-10 ATS keywords missing from the profile for the target role
"""


class LinkedInReviewer:
    """Score and review a LinkedIn profile against a target role.

    Inject a custom ``llm`` in tests to bypass real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.networking_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def review(
        self,
        profile_data: dict[str, Any],
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> LinkedInProfileScore:
        """Review the profile and return a scored assessment.

        Falls back to a heuristic score when all LLM retries are exhausted.
        """
        with _tracer.start_as_current_span("networking.linkedin_review") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("target_role", target_role)
            t0 = time.monotonic()

            try:
                result = await self._review_with_llm(profile_data, target_role, correlation_id)
                NET_LINKEDIN_REVIEW_TOTAL.labels(status="llm").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "networking.linkedin_review_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    correlation_id=correlation_id,
                )
                result = _heuristic_review(profile_data, target_role)
                NET_LINKEDIN_REVIEW_TOTAL.labels(status="fallback").inc()

            duration = time.monotonic() - t0
            NET_LINKEDIN_REVIEW_DURATION.observe(duration)
            span.set_attribute("overall_score", result.overall_score)
            span.set_attribute("ats_score", result.ats_score)
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "networking.linkedin_reviewed",
                target_role=target_role,
                overall_score=result.overall_score,
                ats_score=result.ats_score,
                improvement_count=len(result.improvements),
                keyword_count=len(result.recommended_keywords),
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
    async def _review_with_llm(
        self,
        profile_data: dict[str, Any],
        target_role: str,
        correlation_id: str,
    ) -> LinkedInProfileScore:
        profile_json = json.dumps(profile_data, indent=2)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Target role: {target_role}\n\n"
                        f"LinkedIn profile data:\n{profile_json}"
                    )
                ),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return _build_score(raw)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_score(raw: dict[str, Any]) -> LinkedInProfileScore:
    def _clamp(v: Any, default: float = 0.5) -> float:
        try:
            return round(max(0.0, min(1.0, float(v))), 3)
        except (TypeError, ValueError):
            return default

    headline = _clamp(raw.get("headline_score"))
    summary = _clamp(raw.get("summary_score"))
    experience = _clamp(raw.get("experience_score"))
    skills = _clamp(raw.get("skills_score"))
    ats = _clamp(raw.get("ats_score"))

    overall = _clamp(
        raw.get("overall_score")
        or (headline * 0.20 + summary * 0.25 + experience * 0.30 + skills * 0.15 + ats * 0.10)
    )

    return LinkedInProfileScore(
        headline_score=headline,
        summary_score=summary,
        experience_score=experience,
        skills_score=skills,
        overall_score=overall,
        ats_score=ats,
        strengths=[str(s) for s in raw.get("strengths", []) if s],
        improvements=[str(i) for i in raw.get("improvements", []) if i],
        recommended_keywords=[str(k) for k in raw.get("recommended_keywords", []) if k],
    )


def _heuristic_review(profile_data: dict[str, Any], target_role: str) -> LinkedInProfileScore:
    """Minimal fallback review when the LLM is unavailable."""
    completeness = float(profile_data.get("profile_completeness", 0.65))
    return LinkedInProfileScore(
        headline_score=round(completeness, 3),
        summary_score=round(completeness * 0.9, 3),
        experience_score=round(completeness * 0.85, 3),
        skills_score=round(completeness * 0.8, 3),
        overall_score=round(completeness * 0.85, 3),
        ats_score=round(completeness * 0.7, 3),
        strengths=["Profile data successfully retrieved"],
        improvements=[
            f"Tailor your headline specifically for '{target_role}'",
            "Quantify achievements in experience descriptions (numbers, impact, scale)",
            f"Add keywords relevant to {target_role} in your skills section",
            "Expand your summary to include career transition motivation",
        ],
        recommended_keywords=[target_role],
    )
