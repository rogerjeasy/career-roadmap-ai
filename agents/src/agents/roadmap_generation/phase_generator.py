"""PhaseGenerator — LLM: build structured learning phases from gap + market data.

Falls back to a deterministic 3-phase plan when the LLM call fails, so the
pipeline never stalls on this step.
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
    ROADMAP_PHASE_GEN_DURATION,
    ROADMAP_PHASE_GEN_TOTAL,
    get_tracer,
)
from agents.roadmap_generation.models import DifficultyLevel, Phase

logger = get_logger(__name__)
_tracer = get_tracer("agents.roadmap_generation.phase_generator")

_SYSTEM_PROMPT = """\
You are an expert career roadmap architect. Design a structured, phased learning plan
that closes skill gaps efficiently, ordered by prerequisite dependency, and grounded
in real market demand.

OUTPUT — valid JSON only (no code fences, no markdown):
{
  "phases": [
    {
      "index": 1,
      "title": "Short phase title",
      "description": "What this phase covers and why it comes first",
      "duration_weeks": 6,
      "goals": ["Build X that does Y", "Deploy Z to production"],
      "skills_to_acquire": ["Skill1", "Skill2"],
      "gaps_addressed": ["exact_gap_name_from_input"],
      "market_relevance": "Cite specific numbers from the input data",
      "difficulty": "beginner"
    }
  ]
}

RULES:
1. Generate exactly 3–5 phases for any timeline
2. Sum of all duration_weeks MUST equal total_weeks (provided in input)
3. Phase difficulty must progress: beginner → intermediate → advanced
4. Assign every CRITICAL and HIGH severity gap to the earliest suitable phase
5. Incorporate trending skills where they overlap with required gaps
6. market_relevance must quote specific input data (job count, salary, skill signal count)
7. All goals must start with an action verb and be deliverable within the phase
8. gaps_addressed values must exactly match gap names from the prioritised_gaps input
9. skills_to_acquire should be learnable within duration_weeks at weekly_hours_available
10. Do not invent facts not present in the input
"""


class PhaseGenerator:
    """Generates structured learning phases from gap analysis and market intelligence.

    Inject a custom ``llm`` in tests to avoid real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.roadmap_generation_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=3072,
            temperature=0.2,
        )

    async def generate(
        self,
        target_role: str,
        timeline_months: int,
        weekly_hours: int,
        prioritised_gaps: list[dict],
        trending_skills: list[dict],
        salary_benchmark: dict | None,
        job_posting_count: int,
        *,
        correlation_id: str = "",
    ) -> list[Phase]:
        """Return LLM-generated phases. Falls back to a heuristic plan on failure."""
        with _tracer.start_as_current_span("roadmap.phase_generation") as span:
            span.set_attribute("target_role", target_role)
            span.set_attribute("timeline_months", timeline_months)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                phases = await self._generate_with_llm(
                    target_role,
                    timeline_months,
                    weekly_hours,
                    prioritised_gaps,
                    trending_skills,
                    salary_benchmark,
                    job_posting_count,
                    correlation_id,
                )
                ROADMAP_PHASE_GEN_TOTAL.labels(status="llm").inc()
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "roadmap.phase_gen_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    correlation_id=correlation_id,
                )
                phases = _fallback_phases(target_role, timeline_months, prioritised_gaps)
                ROADMAP_PHASE_GEN_TOTAL.labels(status="fallback").inc()

            ROADMAP_PHASE_GEN_DURATION.observe(time.monotonic() - t0)
            logger.info(
                "roadmap.phases_generated",
                phase_count=len(phases),
                target_role=target_role,
                correlation_id=correlation_id,
            )
            return phases

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _generate_with_llm(
        self,
        target_role: str,
        timeline_months: int,
        weekly_hours: int,
        prioritised_gaps: list[dict],
        trending_skills: list[dict],
        salary_benchmark: dict | None,
        job_posting_count: int,
        correlation_id: str,
    ) -> list[Phase]:
        user_content = _build_user_prompt(
            target_role,
            timeline_months,
            weekly_hours,
            prioritised_gaps,
            trending_skills,
            salary_benchmark,
            job_posting_count,
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict) or "phases" not in raw:
            raise ValueError("LLM response missing 'phases' key")
        return [_parse_phase(p, i + 1) for i, p in enumerate(raw["phases"])]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_user_prompt(
    target_role: str,
    timeline_months: int,
    weekly_hours: int,
    prioritised_gaps: list[dict],
    trending_skills: list[dict],
    salary_benchmark: dict | None,
    job_posting_count: int,
) -> str:
    total_weeks = timeline_months * 4
    lines = [
        f"Target role: {target_role}",
        f"Timeline: {timeline_months} months ({total_weeks} total_weeks — phases must sum to this)",
        f"Study hours per week: {weekly_hours}h",
        f"Active job postings: {job_posting_count}",
    ]

    if salary_benchmark and salary_benchmark.get("median_annual"):
        lines.append(
            f"Salary benchmark: median {salary_benchmark['median_annual']:,} "
            f"{salary_benchmark.get('currency', 'USD')}/yr"
        )

    critical_high = [
        g for g in prioritised_gaps
        if g.get("severity") in ("critical", "high") and g.get("is_required")
    ][:10]
    other_gaps = [g for g in prioritised_gaps if g not in critical_high][:8]

    if critical_high:
        lines.append("\nCRITICAL/HIGH priority gaps (must address first):")
        for g in critical_high:
            lines.append(
                f"  - {g['requirement_name']} "
                f"(severity: {g['severity']}, diff_score: {g.get('diff_score', 0):.2f})"
            )

    if other_gaps:
        lines.append("\nOther gaps (incorporate where timeline allows):")
        for g in other_gaps:
            lines.append(f"  - {g['requirement_name']} (severity: {g['severity']})")

    if trending_skills:
        lines.append("\nTop trending market skills:")
        for s in trending_skills[:8]:
            lines.append(
                f"  - {s['name']} "
                f"({s.get('signal_count', 0)} signals, {s.get('trend_direction', 'stable')})"
            )

    return "\n".join(lines)


def _parse_phase(raw: dict[str, Any], default_index: int) -> Phase:
    raw_diff = str(raw.get("difficulty", "beginner")).lower()
    try:
        difficulty = DifficultyLevel(raw_diff)
    except ValueError:
        difficulty = DifficultyLevel.BEGINNER

    return Phase(
        index=int(raw.get("index", default_index)),
        title=str(raw.get("title", f"Phase {default_index}")),
        description=str(raw.get("description", "")),
        duration_weeks=max(1, int(raw.get("duration_weeks", 4))),
        goals=_to_str_list(raw.get("goals", [])),
        skills_to_acquire=_to_str_list(raw.get("skills_to_acquire", [])),
        gaps_addressed=_to_str_list(raw.get("gaps_addressed", [])),
        market_relevance=str(raw.get("market_relevance", "")),
        difficulty=difficulty,
    )


def _to_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    return []


def _fallback_phases(
    target_role: str,
    timeline_months: int,
    prioritised_gaps: list[dict],
) -> list[Phase]:
    """Deterministic 3-phase fallback when LLM fails."""
    total_weeks = timeline_months * 4
    durations = _split_weeks(total_weeks, 3)

    critical = [g["requirement_name"] for g in prioritised_gaps if g.get("severity") == "critical"][:5]
    high = [g["requirement_name"] for g in prioritised_gaps if g.get("severity") == "high"][:5]
    others = [
        g["requirement_name"]
        for g in prioritised_gaps
        if g.get("severity") not in ("critical", "high")
    ][:5]

    return [
        Phase(
            index=1,
            title="Foundation Building",
            description=f"Close critical skill gaps and establish core competencies for {target_role}.",
            duration_weeks=durations[0],
            goals=["Build foundational skills for the role", "Complete at least one portfolio project"],
            skills_to_acquire=critical or ["core technical skills"],
            gaps_addressed=critical,
            market_relevance=f"Critical skills for {target_role} with current market demand.",
            difficulty=DifficultyLevel.BEGINNER,
        ),
        Phase(
            index=2,
            title="Applied Skills Development",
            description="Build applied, job-ready competencies addressing high-priority gaps.",
            duration_weeks=durations[1],
            goals=["Apply skills in realistic projects", "Build portfolio demonstrating job readiness"],
            skills_to_acquire=high or ["applied technical skills"],
            gaps_addressed=high,
            market_relevance=f"High-demand skills for {target_role} in the current hiring market.",
            difficulty=DifficultyLevel.INTERMEDIATE,
        ),
        Phase(
            index=3,
            title="Advanced Specialisation",
            description="Develop advanced, differentiating expertise to stand out as a candidate.",
            duration_weeks=durations[2],
            goals=["Demonstrate advanced competencies", "Complete a capstone portfolio project"],
            skills_to_acquire=others or ["advanced specialisation"],
            gaps_addressed=others,
            market_relevance=f"Differentiating skills that elevate candidate standing for {target_role}.",
            difficulty=DifficultyLevel.ADVANCED,
        ),
    ]


def _split_weeks(total: int, n: int) -> list[int]:
    """Distribute total_weeks into n integers that sum to total."""
    base, remainder = divmod(max(total, n), n)
    return [base + (1 if i < remainder else 0) for i in range(n)]
