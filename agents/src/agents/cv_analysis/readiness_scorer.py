"""ReadinessScorer — compute a role-readiness score from SkillGraph + ParsedCV.

Uses the candidate's SkillGraph and ParsedCV (experience, education) together
with the target role to produce a ReadinessResult that includes:
  - An overall weighted score (0–1)
  - A five-dimension breakdown
  - Lists of matched / missing skills
  - 3–5 actionable recommendations

Scoring is LLM-based for semantic accuracy (a skill node may satisfy a
requirement even under a different name). Falls back to a local heuristic
when the LLM is unavailable so the pipeline never hard-fails.

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
from agents.core.observability import CV_READINESS_DURATION, CV_READINESS_SCORE, get_tracer
from agents.cv_analysis.models import ParsedCV, ReadinessBreakdown, ReadinessResult, SkillGraph

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.readiness_scorer")

# Dimension weights must sum to 1.0
_WEIGHTS = {
    "required_skills_matched": 0.35,
    "preferred_skills_matched": 0.15,
    "experience_level_match": 0.25,
    "education_match": 0.10,
    "domain_alignment": 0.15,
}

_SYSTEM_PROMPT = """\
You are a career readiness assessor. Given a candidate's skills and background
and a target role, assess their readiness and return ONLY valid JSON (no fences):
{
  "required_skills_matched": 0.0-1.0,
  "preferred_skills_matched": 0.0-1.0,
  "experience_level_match": 0.0-1.0,
  "education_match": 0.0-1.0,
  "domain_alignment": 0.0-1.0,
  "matched_skills": ["candidate skills that satisfy role requirements"],
  "missing_required_skills": ["required skills the candidate lacks"],
  "missing_preferred_skills": ["preferred skills the candidate lacks"],
  "recommendations": ["3-5 concise actionable steps to close the gaps"]
}

Scoring guidance:
- required_skills_matched: fraction of must-have skills covered by the candidate
- preferred_skills_matched: fraction of nice-to-have skills covered
- experience_level_match: 1.0 if experience meets typical requirement; scale down linearly
- education_match: 1.0 for directly relevant degree; 0.7 adjacent field; 0.4 unrelated; 0.5 if unknown
- domain_alignment: how closely the candidate's work domain overlaps with the target role's domain
- recommendations: most impactful 3-5 actions, specific not generic (name actual skills/courses/certs)
"""


class ReadinessScorer:
    """Compute a role-readiness score using candidate profile + target role.

    Inject a custom ``llm`` in tests to bypass real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def score(
        self,
        parsed_cv: ParsedCV,
        skill_graph: SkillGraph,
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> ReadinessResult:
        """Compute the readiness score for ``target_role``.

        Falls back to a heuristic-only result when the LLM call fails after
        all retries, so the pipeline always returns a valid result.
        """
        with _tracer.start_as_current_span("cv.readiness_score") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("target_role", target_role)
            span.set_attribute("skill_count", len(skill_graph.nodes))
            t0 = time.monotonic()

            try:
                result = await self._score_with_llm(
                    parsed_cv, skill_graph, target_role, correlation_id
                )
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "cv.readiness_score_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    correlation_id=correlation_id,
                )
                result = _heuristic_score(parsed_cv, skill_graph)

            duration = time.monotonic() - t0
            CV_READINESS_DURATION.observe(duration)
            CV_READINESS_SCORE.observe(result.overall_score)

            span.set_attribute("overall_score", result.overall_score)
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "cv.readiness_scored",
                overall_score=result.overall_score,
                matched_skills=len(result.matched_skills),
                missing_required=len(result.missing_required_skills),
                target_role=target_role,
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
    async def _score_with_llm(
        self,
        parsed_cv: ParsedCV,
        skill_graph: SkillGraph,
        target_role: str,
        correlation_id: str,
    ) -> ReadinessResult:
        prompt = _build_scoring_prompt(parsed_cv, skill_graph, target_role)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return _build_readiness_result(raw)


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_scoring_prompt(
    parsed_cv: ParsedCV,
    skill_graph: SkillGraph,
    target_role: str,
) -> str:
    exp_lines = "\n".join(
        f"- {e.title} at {e.company} ({e.duration_months or '?'} months)"
        for e in parsed_cv.experience
    ) or "none"
    edu_lines = "\n".join(
        f"- {e.degree or 'Degree'} in {e.field_of_study or 'N/A'} from {e.institution}"
        for e in parsed_cv.education
    ) or "none"
    skills_str = ", ".join(skill_graph.canonical_names) or "none listed"
    total_exp = (
        f"{parsed_cv.total_experience_months} months"
        if parsed_cv.total_experience_months
        else "unknown"
    )
    return (
        f"Target role: {target_role}\n\n"
        f"Total professional experience: {total_exp}\n\n"
        f"Skills: {skills_str}\n\n"
        f"Work experience:\n{exp_lines}\n\n"
        f"Education:\n{edu_lines}"
    )


def _build_readiness_result(raw: dict[str, Any]) -> ReadinessResult:
    breakdown = ReadinessBreakdown(
        required_skills_matched=_clamp(raw.get("required_skills_matched", 0.0)),
        preferred_skills_matched=_clamp(raw.get("preferred_skills_matched", 0.0)),
        experience_level_match=_clamp(raw.get("experience_level_match", 0.0)),
        education_match=_clamp(raw.get("education_match", 0.0)),
        domain_alignment=_clamp(raw.get("domain_alignment", 0.0)),
    )
    overall = round(
        breakdown.required_skills_matched * _WEIGHTS["required_skills_matched"]
        + breakdown.preferred_skills_matched * _WEIGHTS["preferred_skills_matched"]
        + breakdown.experience_level_match * _WEIGHTS["experience_level_match"]
        + breakdown.education_match * _WEIGHTS["education_match"]
        + breakdown.domain_alignment * _WEIGHTS["domain_alignment"],
        3,
    )
    return ReadinessResult(
        overall_score=overall,
        breakdown=breakdown,
        matched_skills=[str(s) for s in raw.get("matched_skills", [])],
        missing_required_skills=[str(s) for s in raw.get("missing_required_skills", [])],
        missing_preferred_skills=[str(s) for s in raw.get("missing_preferred_skills", [])],
        recommendations=[str(r) for r in raw.get("recommendations", [])],
    )


def _heuristic_score(parsed_cv: ParsedCV, skill_graph: SkillGraph) -> ReadinessResult:
    """Simple fallback when LLM scoring is unavailable.

    Education and domain alignment are omitted (scored 0) because without LLM
    context we cannot assess them — this keeps the fallback score conservative
    and proportional to measurable signals only.
    """
    exp_score = min(1.0, (parsed_cv.total_experience_months or 0) / 60)   # 5 yrs → 1.0
    skill_score = min(1.0, len(skill_graph.nodes) / 15)                    # 15 skills → 1.0
    overall = round(
        skill_score * (_WEIGHTS["required_skills_matched"] + _WEIGHTS["preferred_skills_matched"])
        + exp_score * _WEIGHTS["experience_level_match"],
        3,
    )
    return ReadinessResult(
        overall_score=overall,
        breakdown=ReadinessBreakdown(
            required_skills_matched=skill_score,
            preferred_skills_matched=skill_score * 0.7,
            experience_level_match=exp_score,
            education_match=0.0,
            domain_alignment=0.0,
        ),
        matched_skills=skill_graph.canonical_names[:10],
        missing_required_skills=[],
        missing_preferred_skills=[],
        recommendations=["LLM scoring unavailable — enable for personalised recommendations."],
    )


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
