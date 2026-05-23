"""PhaseGenerator — LLM: build structured learning phases from gap + market data.

Provider cascade: Claude (primary) → OpenAI (secondary) → DeepSeek (tertiary).
If every provider fails, a RuntimeError is raised — no generic/synthetic data is substituted,
because hardcoded phases would be incorrect for careers in medicine, law, finance, arts, etc.

Two prompt modes:
  • Grounded mode  — market data available; LLM must cite input figures.
  • Research mode  — market data sparse/absent; LLM draws on training knowledge
                     to estimate salary ranges, skill demand, and job-market context.

Phase output is enriched beyond the basic schema:
  • sample_weekly_schedule  — realistic day-by-day schedule for the phase week
  • monthly_goals           — one concrete goal per calendar month in the phase
  • book_recommendations    — curated book list (title + author + rationale)
"""
from __future__ import annotations

import json
import time
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.core.llm_provider import RESEARCH_MODE_PREFIX, llm_generate
from agents.core.logging import get_logger
from agents.core.observability import (
    ROADMAP_PHASE_GEN_DURATION,
    ROADMAP_PHASE_GEN_TOTAL,
    get_tracer,
)
from agents.roadmap_generation.models import (
    ActionItem,
    DailyActivity,
    DifficultyLevel,
    Phase,
    SkillItem,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.roadmap_generation.phase_generator")

# ── System prompts ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_BASE = """\
You are an expert career roadmap architect with deep knowledge of career transitions,
skill development, and job markets across every industry and country worldwide.
Design a structured, phased learning plan that closes skill gaps efficiently,
ordered by prerequisite dependency, and grounded in real market demand.

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
      "skills": [
        {"text": "Skill1", "is_priority": true, "display_order": 0},
        {"text": "Skill2", "is_priority": false, "display_order": 1}
      ],
      "actions": [
        {
          "text": "Set up your development environment",
          "sub_text": "Install required tools and configure your workspace before writing any code",
          "display_order": 0
        },
        {
          "text": "Complete the core learning module",
          "sub_text": "Focus on hands-on exercises — don't just read, build something each session",
          "display_order": 1
        }
      ],
      "gaps_addressed": ["exact_gap_name_from_input"],
      "market_relevance": "Cite specific data or realistic estimates for this role/location",
      "difficulty": "beginner",
      "sample_weekly_schedule": [
        {
          "day": "Monday",
          "activity": "60min: study theory + 30min: solve 1 coding exercise",
          "duration_minutes": 90,
          "category": "technical"
        },
        {
          "day": "Tuesday",
          "activity": "90min: build a feature for your portfolio project",
          "duration_minutes": 90,
          "category": "technical"
        },
        {
          "day": "Wednesday",
          "activity": "30min: LinkedIn networking + 30min: industry news reading",
          "duration_minutes": 60,
          "category": "networking"
        },
        {
          "day": "Thursday",
          "activity": "60min: code review + 30min: write documentation",
          "duration_minutes": 90,
          "category": "technical"
        },
        {
          "day": "Friday",
          "activity": "45min: review week progress and plan next week",
          "duration_minutes": 45,
          "category": "reflection"
        },
        {
          "day": "Saturday",
          "activity": "3h: extended project work or deep-dive tutorial",
          "duration_minutes": 180,
          "category": "technical"
        },
        {
          "day": "Sunday",
          "activity": "60min: read tech book or watch educational video content",
          "duration_minutes": 60,
          "category": "soft_skill"
        }
      ],
      "monthly_goals": [
        "Month 1: Set up development environment and complete 2 beginner exercises",
        "Month 2: Build a complete feature that demonstrates all learned concepts"
      ],
      "book_recommendations": [
        "Clean Code by Robert C. Martin (2008) — coding standards and maintainability fundamentals",
        "The Pragmatic Programmer by Andrew Hunt & David Thomas (2019) — career and craft mindset"
      ]
    }
  ]
}

RULES:
1.  Generate exactly 3–5 phases for any timeline
2.  Sum of all duration_weeks MUST equal total_weeks (provided in input)
3.  Phase difficulty must progress: beginner → intermediate → advanced
4.  Assign every CRITICAL and HIGH severity gap to the earliest suitable phase
5.  Incorporate trending skills where they overlap with required gaps
6.  market_relevance must include salary context and skill demand context
7.  All goals must start with an action verb and be deliverable within the phase
8.  gaps_addressed values must exactly match gap names from the prioritised_gaps input
9.  skills_to_acquire (flat list) and skills (structured list) must contain the same skills
10. Mark the 2-3 most critical skills as is_priority: true in the skills array
11. actions: provide 3-5 concrete, ordered steps a learner must take during this phase
12. Each action sub_text must explain WHY or HOW, adding context beyond the action text
13. skills and actions display_order must start at 0 and increment by 1
14. sample_weekly_schedule: cover all 7 days; tailor activities to the phase skills and difficulty
15. monthly_goals: one specific, measurable goal per calendar month in the phase duration
16. book_recommendations: name at least 2 specific books with author, year, and one-line rationale;
    include at least one free or open-access resource; cover both foundational and advanced reading
"""

_GROUNDED_SUFFIX = """
17. Do not invent salary figures or market statistics not present in the input data.
    Quote specific numbers from the input wherever available.
"""

_RESEARCH_SUFFIX = """
17. RESEARCH MODE: market data was not returned by the pipeline. You MUST:
    - Estimate a realistic salary range for this role and region in market_relevance
    - Describe in-demand skills and hiring trends from your training knowledge
    - Label all estimates clearly as "estimated" in market_relevance text
    Do NOT leave market_relevance blank or write "data unavailable".
"""


def _build_system_prompt(data_sparse: bool) -> str:
    if data_sparse:
        return RESEARCH_MODE_PREFIX + _SYSTEM_PROMPT_BASE + _RESEARCH_SUFFIX
    return _SYSTEM_PROMPT_BASE + _GROUNDED_SUFFIX


# ── PhaseGenerator ────────────────────────────────────────────────────────────


class PhaseGenerator:
    """Generates structured learning phases from gap analysis and market intelligence.

    Supports multi-LLM cascade (Claude → OpenAI → DeepSeek) and research mode
    for sparse/absent market data.
    """

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
        data_sparse: bool = False,
        correlation_id: str = "",
    ) -> list[Phase]:
        """Return LLM-generated phases. Raises RuntimeError if all providers fail — no synthetic fallback."""
        with _tracer.start_as_current_span("roadmap.phase_generation") as span:
            span.set_attribute("target_role", target_role)
            span.set_attribute("timeline_months", timeline_months)
            span.set_attribute("data_sparse", data_sparse)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                phases, provider = await self._generate_with_cascade(
                    target_role,
                    timeline_months,
                    weekly_hours,
                    prioritised_gaps,
                    trending_skills,
                    salary_benchmark,
                    job_posting_count,
                    data_sparse=data_sparse,
                    correlation_id=correlation_id,
                )
                ROADMAP_PHASE_GEN_TOTAL.labels(status=f"llm_{provider}").inc()
                span.set_attribute("llm_provider", provider)
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                ROADMAP_PHASE_GEN_TOTAL.labels(status="failed").inc()
                logger.error(
                    "roadmap.phase_gen_all_providers_failed",
                    target_role=target_role,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                # Re-raise: the agent layer will surface a clear failure to the user.
                # Generic/fixed phases must never substitute here — they would be
                # wrong for careers in medicine, law, finance, arts, or any domain
                # not represented in a hardcoded template.
                raise RuntimeError(
                    f"Career roadmap generation failed for role '{target_role}': "
                    "all AI providers (Claude, OpenAI, DeepSeek) are currently unavailable. "
                    "Please try again in a few minutes."
                ) from exc

            ROADMAP_PHASE_GEN_DURATION.observe(time.monotonic() - t0)
            logger.info(
                "roadmap.phases_generated",
                phase_count=len(phases),
                target_role=target_role,
                correlation_id=correlation_id,
            )
            return phases

    async def _generate_with_cascade(
        self,
        target_role: str,
        timeline_months: int,
        weekly_hours: int,
        prioritised_gaps: list[dict],
        trending_skills: list[dict],
        salary_benchmark: dict | None,
        job_posting_count: int,
        *,
        data_sparse: bool,
        correlation_id: str,
    ) -> tuple[list[Phase], str]:
        system = _build_system_prompt(data_sparse)
        user = _build_user_prompt(
            target_role,
            timeline_months,
            weekly_hours,
            prioritised_gaps,
            trending_skills,
            salary_benchmark,
            job_posting_count,
            data_sparse=data_sparse,
        )
        # Enriched output needs more tokens — especially in research mode.
        max_tokens = 8000 if data_sparse else 6000

        raw_content, provider = await llm_generate(
            system,
            user,
            max_tokens=max_tokens,
            temperature=0.2,
            primary_model=agent_settings.roadmap_generation_model,
            label="roadmap.phase_gen",
        )

        parsed = json.loads(raw_content)
        if not isinstance(parsed, dict) or "phases" not in parsed:
            raise ValueError(f"LLM response missing 'phases' key (provider={provider})")
        return [_parse_phase(p, i + 1) for i, p in enumerate(parsed["phases"])], provider


# ── Prompt builders ───────────────────────────────────────────────────────────


def _build_user_prompt(
    target_role: str,
    timeline_months: int,
    weekly_hours: int,
    prioritised_gaps: list[dict],
    trending_skills: list[dict],
    salary_benchmark: dict | None,
    job_posting_count: int,
    *,
    data_sparse: bool = False,
) -> str:
    total_weeks = timeline_months * 4
    lines = [
        f"Target role: {target_role}",
        f"Timeline: {timeline_months} months ({total_weeks} total_weeks — phases must sum to this)",
        f"Study hours per week: {weekly_hours}h",
        f"Active job postings found: {job_posting_count}"
        + (" (no live data — use training knowledge)" if data_sparse and job_posting_count == 0 else ""),
    ]

    if salary_benchmark and salary_benchmark.get("median_annual"):
        lines.append(
            f"Salary benchmark: median {salary_benchmark['median_annual']:,} "
            f"{salary_benchmark.get('currency', 'USD')}/yr"
        )
    elif data_sparse:
        lines.append(
            "Salary benchmark: not available — estimate a realistic range in market_relevance"
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
    elif data_sparse:
        lines.append(
            "\nTrending skills: not available from live data — "
            "incorporate skills known to be relevant to this role from your training knowledge"
        )

    if data_sparse:
        lines.append(
            "\nIMPORTANT: Enrich every phase with a realistic sample_weekly_schedule, "
            "specific monthly_goals, and at least 2 concrete book_recommendations. "
            "This roadmap may be the user's primary source of guidance; make it comprehensive."
        )

    return "\n".join(lines)


# ── Parsing ───────────────────────────────────────────────────────────────────


def _parse_phase(raw: dict[str, Any], default_index: int) -> Phase:
    raw_diff = str(raw.get("difficulty", "beginner")).lower()
    try:
        difficulty = DifficultyLevel(raw_diff)
    except ValueError:
        difficulty = DifficultyLevel.BEGINNER

    skills_to_acquire = _to_str_list(raw.get("skills_to_acquire", []))

    skills: list[SkillItem] = []
    raw_skills = raw.get("skills", [])
    if isinstance(raw_skills, list):
        for i, s in enumerate(raw_skills):
            if isinstance(s, dict):
                skills.append(SkillItem(
                    text=str(s.get("text", "")),
                    is_priority=bool(s.get("is_priority", False)),
                    display_order=int(s.get("display_order", i)),
                ))
            elif isinstance(s, str):
                skills.append(SkillItem(text=s, is_priority=False, display_order=i))

    if not skills and skills_to_acquire:
        skills = [
            SkillItem(text=sk, is_priority=(i < 2), display_order=i)
            for i, sk in enumerate(skills_to_acquire)
        ]

    actions: list[ActionItem] = []
    raw_actions = raw.get("actions", [])
    if isinstance(raw_actions, list):
        for i, a in enumerate(raw_actions):
            if isinstance(a, dict):
                actions.append(ActionItem(
                    text=str(a.get("text", "")),
                    sub_text=str(a.get("sub_text", "")),
                    display_order=int(a.get("display_order", i)),
                ))
            elif isinstance(a, str):
                actions.append(ActionItem(text=a, sub_text="", display_order=i))

    # Parse enriched fields
    raw_schedule = raw.get("sample_weekly_schedule", [])
    sample_weekly_schedule: list[DailyActivity] = []
    if isinstance(raw_schedule, list):
        for entry in raw_schedule:
            if isinstance(entry, dict):
                sample_weekly_schedule.append(DailyActivity(
                    day=str(entry.get("day", "")),
                    activity=str(entry.get("activity", "")),
                    duration_minutes=int(entry.get("duration_minutes", 30)),
                    category=str(entry.get("category", "technical")),
                ))

    monthly_goals = _to_str_list(raw.get("monthly_goals", []))
    book_recommendations = _to_str_list(raw.get("book_recommendations", []))

    return Phase(
        index=int(raw.get("index", default_index)),
        title=str(raw.get("title", f"Phase {default_index}")),
        description=str(raw.get("description", "")),
        duration_weeks=max(1, int(raw.get("duration_weeks", 4))),
        goals=_to_str_list(raw.get("goals", [])),
        skills_to_acquire=skills_to_acquire,
        skills=skills,
        actions=actions,
        gaps_addressed=_to_str_list(raw.get("gaps_addressed", [])),
        market_relevance=str(raw.get("market_relevance", "")),
        difficulty=difficulty,
        sample_weekly_schedule=sample_weekly_schedule,
        monthly_goals=monthly_goals,
        book_recommendations=book_recommendations,
    )


def _to_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    return []
