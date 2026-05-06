"""SkillGapScorer — compare candidate profile against role requirements.

Takes:
  - candidate_skills : list of canonical skill names (from SkillGraph)
  - parsed_cv_dict   : CV data as dict (from CV analysis output)
  - role_profile     : RoleProfile (from RoleProfiler)

Produces:
  - list[SkillGap] — one entry per unmet requirement (diff_score > 0.05)
  - DimensionScores — aggregated gap score per dimension

LLM-based for semantic matching: "TypeScript" can partially satisfy a
"JavaScript" requirement. Falls back to name-matching heuristic when the
LLM fails so the pipeline never hard-fails.

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
    GAP_SKILL_SCORE_DURATION,
    GAP_SKILL_SCORE_TOTAL,
    get_tracer,
)
from agents.gap_analysis.models import (
    DimensionScores,
    GapDimension,
    GapSeverity,
    RoleProfile,
    SkillGap,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.gap_analysis.skill_gap_scorer")

_SYSTEM_PROMPT = """\
You are a career gap analyst. Given a candidate's skills/CV and a target role's
requirements, identify the gaps and return ONLY valid JSON (no fences):
{
  "gaps": [
    {
      "requirement_name": "<requirement name exactly as given>",
      "dimension": "tech_skill|soft_skill|certification|portfolio|keyword",
      "diff_score": 0.0-1.0,
      "current_level": "beginner|intermediate|advanced|expert|null",
      "required_level": "beginner|intermediate|advanced|expert|null",
      "roi_score": 0.0-1.0,
      "urgency_score": 0.0-1.0,
      "evidence": "<one-line reason why this gap exists>"
    }
  ]
}

Scoring guidance:
- diff_score: 0.0=fully met, 1.0=completely absent, 0.5=partially met.
  Use semantic matching — "TypeScript" partially satisfies "JavaScript".
- Only return requirements with diff_score > 0.05; omit fully met skills.
- roi_score: 0.0-1.0 — how much closing this gap improves hiring chances.
  High (0.7-1.0) for required tech skills; medium (0.4-0.6) for preferred;
  lower (0.2-0.4) for soft skills already demonstrated elsewhere.
- urgency_score: 0.0-1.0 — how soon this needs addressing.
  High for required; lower for nice-to-haves.
"""


class SkillGapScorer:
    """Identify and score gaps between candidate profile and role requirements.

    Inject a custom ``llm`` in tests to bypass real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=4096,
            temperature=0.0,
        )

    async def score(
        self,
        candidate_skills: list[str],
        parsed_cv_dict: dict[str, Any],
        role_profile: RoleProfile,
        *,
        correlation_id: str = "",
    ) -> tuple[list[SkillGap], DimensionScores]:
        """Identify gaps and compute per-dimension scores.

        Returns ``(gaps, dimension_scores)``. Falls back to heuristic name
        matching when the LLM call fails after all retries.
        """
        with _tracer.start_as_current_span("gap.skill_score") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("candidate_skill_count", len(candidate_skills))
            span.set_attribute("requirement_count", len(role_profile.requirements))
            t0 = time.monotonic()

            try:
                gaps = await self._score_with_llm(
                    candidate_skills, parsed_cv_dict, role_profile, correlation_id
                )
                GAP_SKILL_SCORE_TOTAL.labels(status="llm").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "gap.skill_score_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    correlation_id=correlation_id,
                )
                gaps = _heuristic_gaps(candidate_skills, role_profile)
                GAP_SKILL_SCORE_TOTAL.labels(status="fallback").inc()

            dim_scores = _compute_dimension_scores(gaps)

            duration = time.monotonic() - t0
            GAP_SKILL_SCORE_DURATION.observe(duration)
            span.set_attribute("gap_count", len(gaps))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "gap.skill_scored",
                gap_count=len(gaps),
                critical_count=sum(1 for g in gaps if g.severity == GapSeverity.CRITICAL),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return gaps, dim_scores

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _score_with_llm(
        self,
        candidate_skills: list[str],
        parsed_cv_dict: dict[str, Any],
        role_profile: RoleProfile,
        correlation_id: str,
    ) -> list[SkillGap]:
        prompt = _build_scoring_prompt(candidate_skills, parsed_cv_dict, role_profile)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return _build_gaps(raw.get("gaps", []), role_profile)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_scoring_prompt(
    candidate_skills: list[str],
    parsed_cv_dict: dict[str, Any],
    role_profile: RoleProfile,
) -> str:
    skills_str = ", ".join(candidate_skills) or "none listed"
    certs_str = ", ".join(parsed_cv_dict.get("certifications", [])) or "none"
    exp_months = parsed_cv_dict.get("total_experience_months") or "unknown"
    req_lines = "\n".join(
        f"- [{req.dimension.value}] {'REQUIRED' if req.is_required else 'preferred'} "
        f"{req.name} (level: {req.typical_level or 'any'})"
        for req in role_profile.requirements
    )
    return (
        f"Target role: {role_profile.role_title}\n\n"
        f"Candidate skills: {skills_str}\n\n"
        f"Candidate certifications: {certs_str}\n\n"
        f"Total experience: {exp_months} months\n\n"
        f"Role requirements:\n{req_lines}\n\n"
        f"ATS keywords needed: {', '.join(role_profile.keywords) or 'none'}"
    )


def _build_gaps(raw_gaps: list[Any], role_profile: RoleProfile) -> list[SkillGap]:
    req_lookup = {r.name.lower(): r for r in role_profile.requirements}
    gaps: list[SkillGap] = []
    for item in raw_gaps:
        if not isinstance(item, dict) or not item.get("requirement_name"):
            continue
        diff = _clamp(item.get("diff_score", 1.0))
        if diff <= 0.05:
            continue
        req_name = str(item["requirement_name"])
        req = req_lookup.get(req_name.lower())
        is_required = req.is_required if req else True
        dim_str = str(item.get("dimension", "tech_skill"))
        try:
            dimension = GapDimension(dim_str)
        except ValueError:
            dimension = GapDimension.TECH_SKILL
        gaps.append(
            SkillGap(
                requirement_name=req_name,
                dimension=dimension,
                severity=_severity(diff, is_required),
                is_required=is_required,
                diff_score=diff,
                current_level=item.get("current_level") or None,
                required_level=item.get("required_level") or None,
                roi_score=_clamp(item.get("roi_score", 0.5)),
                urgency_score=_clamp(item.get("urgency_score", 0.5)),
                evidence=str(item.get("evidence", "")),
            )
        )
    return gaps


def _heuristic_gaps(
    candidate_skills: list[str],
    role_profile: RoleProfile,
) -> list[SkillGap]:
    """Simple name-match fallback — conservative diff_scores, no LLM."""
    candidate_lower = {s.lower() for s in candidate_skills}
    gaps: list[SkillGap] = []
    for req in role_profile.requirements:
        if req.name.lower() in candidate_lower:
            continue
        diff = 1.0 if req.is_required else 0.6
        gaps.append(
            SkillGap(
                requirement_name=req.name,
                dimension=req.dimension,
                severity=_severity(diff, req.is_required),
                is_required=req.is_required,
                diff_score=diff,
                current_level=None,
                required_level=req.typical_level,
                roi_score=0.8 if req.is_required else 0.4,
                urgency_score=0.9 if req.is_required else 0.3,
                evidence="Skill not found in candidate profile (heuristic match)",
            )
        )
    return gaps


def _compute_dimension_scores(gaps: list[SkillGap]) -> DimensionScores:
    """Weighted-average diff_score per dimension (required gaps weighted 1.5×)."""
    totals: dict[GapDimension, float] = {d: 0.0 for d in GapDimension}
    counts: dict[GapDimension, float] = {d: 0.0 for d in GapDimension}
    for gap in gaps:
        w = 1.5 if gap.is_required else 1.0
        totals[gap.dimension] += gap.diff_score * w
        counts[gap.dimension] += w

    def _avg(dim: GapDimension) -> float:
        if counts[dim] == 0.0:
            return 0.0
        return round(min(1.0, totals[dim] / counts[dim]), 3)

    return DimensionScores(
        tech_skills=_avg(GapDimension.TECH_SKILL),
        soft_skills=_avg(GapDimension.SOFT_SKILL),
        certifications=_avg(GapDimension.CERTIFICATION),
        portfolio=_avg(GapDimension.PORTFOLIO),
        keywords=_avg(GapDimension.KEYWORD),
    )


def _severity(diff: float, is_required: bool) -> GapSeverity:
    if is_required and diff >= 0.7:
        return GapSeverity.CRITICAL
    if is_required and diff >= 0.3:
        return GapSeverity.HIGH
    if not is_required and diff >= 0.5:
        return GapSeverity.MEDIUM
    return GapSeverity.LOW


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
