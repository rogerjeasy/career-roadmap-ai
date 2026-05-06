"""JobScorer — deterministic + LLM-enriched job scoring.

Phase 1 (deterministic): Scores every listing instantly using weighted criteria:
  - Skill overlap (proportion of required skills the user has)   — 50 %
  - Location fit (remote always matches)                          — 20 %
  - Salary fit (listing max vs. user salary goal)                 — 15 %
  - Seniority alignment                                           — 15 %

Phase 2 (LLM enrichment): Calls Claude on the top-N listings to generate
natural-language match_reasons and critical missing_skills. Falls back
silently if the LLM is unavailable — the deterministic scores are still valid.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.contracts.tasks import UserProfileSnapshot
from agents.core.logging import get_logger
from agents.core.observability import OPP_MATCH_SCORE, OPP_SCORE_DURATION, OPP_SCORE_TOTAL
from agents.opportunity.models import JobListing, JobMatchScore

logger = get_logger(__name__)

_HIGH_MATCH_THRESHOLD = 0.65
_ENRICH_TOP_N = 10
_PROMPTS_DIR = Path(__file__).parent / "prompts"

_SKILL_WEIGHT = 0.50
_LOCATION_WEIGHT = 0.20
_SALARY_WEIGHT = 0.15
_SENIORITY_WEIGHT = 0.15

_SENIOR_TERMS = {"senior", "lead", "principal", "staff", "architect"}
_JUNIOR_TERMS = {"junior", "associate", "entry"}


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


class JobScorer:
    """Scores job listings against a user profile.

    Parameters
    ----------
    llm:
        LangChain LLM for Phase 2 enrichment. When ``None``, only deterministic
        scores are returned and the agent still functions correctly.
    """

    def __init__(self, *, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm
        self._system_prompt = _load_prompt("opportunity_system.txt")

    def score_all(
        self,
        listings: list[JobListing],
        profile: UserProfileSnapshot,
    ) -> list[JobMatchScore]:
        """Score all listings deterministically and return sorted by score (desc)."""
        scored = [_deterministic_score(listing, profile) for listing in listings]
        scored.sort(key=lambda j: j.match_score, reverse=True)
        for job in scored:
            OPP_MATCH_SCORE.observe(job.match_score)
        return scored

    async def enrich_top(
        self,
        scored: list[JobMatchScore],
        profile: UserProfileSnapshot,
    ) -> list[JobMatchScore]:
        """Enrich the top-N scored jobs with LLM-generated match reasons.

        Falls back silently if the LLM fails — the caller always receives the
        original ``scored`` list, possibly with ``match_reasons`` populated.
        """
        if self._llm is None or not scored:
            return scored

        top = scored[:_ENRICH_TOP_N]
        t0 = time.monotonic()
        try:
            user_prompt = _build_enrichment_prompt(top, profile)
            response = await self._llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=user_prompt),
            ])
            raw = str(response.content).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            enrichments: list[dict[str, Any]] = json.loads(raw)
            _apply_enrichments(top, enrichments)
            OPP_SCORE_TOTAL.labels(status="llm").inc()
        except Exception as exc:
            logger.warning("opportunity.scorer.enrich_failed", error=str(exc))
            OPP_SCORE_TOTAL.labels(status="fallback").inc()
        finally:
            OPP_SCORE_DURATION.observe(time.monotonic() - t0)

        return scored


# ── Deterministic scoring ──────────────────────────────────────────────────────


def _deterministic_score(listing: JobListing, profile: UserProfileSnapshot) -> JobMatchScore:
    user_skills_lower = {s.lower() for s in profile.skills}
    required_lower = [s.lower() for s in listing.required_skills]

    skill_overlap = [s for s in listing.required_skills if s.lower() in user_skills_lower]
    missing_skills = [s for s in listing.required_skills if s.lower() not in user_skills_lower]
    skill_score = len(skill_overlap) / max(len(required_lower), 1)

    location_fit = listing.remote or _location_matches(listing.location, profile.location)
    location_score = 1.0 if location_fit else 0.3

    salary_fit: bool | None = None
    salary_score = 1.0
    if profile.salary_goal and listing.salary_max:
        salary_fit = listing.salary_max >= profile.salary_goal * 0.85
        salary_score = 1.0 if salary_fit else 0.5

    seniority_score = _seniority_match(
        listing.seniority_level, profile.current_role, profile.target_role
    )

    match_score = (
        skill_score * _SKILL_WEIGHT
        + location_score * _LOCATION_WEIGHT
        + salary_score * _SALARY_WEIGHT
        + seniority_score * _SENIORITY_WEIGHT
    )

    return JobMatchScore(
        listing=listing,
        match_score=round(match_score, 3),
        skill_overlap=skill_overlap,
        missing_skills=missing_skills[:10],
        salary_fit=salary_fit,
        location_fit=location_fit,
        is_high_match=match_score >= _HIGH_MATCH_THRESHOLD,
    )


def _location_matches(listing_loc: str, user_loc: str | None) -> bool:
    if not user_loc or not listing_loc:
        return True
    return user_loc.lower().strip() in listing_loc.lower()


def _seniority_match(
    seniority: str | None,
    current_role: str | None,
    target_role: str | None,
) -> float:
    if not seniority:
        return 0.8

    seniority_lower = seniority.lower()
    context = f"{current_role or ''} {target_role or ''}".lower()

    listing_is_senior = any(t in seniority_lower for t in _SENIOR_TERMS)
    listing_is_junior = any(t in seniority_lower for t in _JUNIOR_TERMS)
    profile_is_senior = any(t in context for t in _SENIOR_TERMS)
    profile_is_junior = any(t in context for t in _JUNIOR_TERMS)

    if listing_is_senior and profile_is_senior:
        return 1.0
    if listing_is_junior and profile_is_junior:
        return 1.0
    if listing_is_senior and profile_is_junior:
        return 0.4
    if listing_is_junior and profile_is_senior:
        return 0.5
    return 0.8


# ── LLM enrichment helpers ─────────────────────────────────────────────────────


def _build_enrichment_prompt(top: list[JobMatchScore], profile: UserProfileSnapshot) -> str:
    profile_section = (
        f"User profile:\n"
        f"- Current role: {profile.current_role or 'not specified'}\n"
        f"- Target role: {profile.target_role or 'not specified'}\n"
        f"- Skills: {', '.join(profile.skills[:25])}\n"
        f"- Location: {profile.location or 'not specified'}\n"
        f"- Timeline: {profile.timeline_months} months\n"
    )
    listings_section = "Job listings to enrich (JSON array):\n" + json.dumps(
        [
            {
                "index": i,
                "id": job.listing.id,
                "title": job.listing.title,
                "company": job.listing.company,
                "required_skills": job.listing.required_skills,
                "description": job.listing.description[:400],
                "match_score": job.match_score,
                "skill_overlap": job.skill_overlap,
                "missing_skills": job.missing_skills,
            }
            for i, job in enumerate(top)
        ],
        indent=2,
    )
    return (
        f"{profile_section}\n\n"
        f"{listings_section}\n\n"
        "Return a JSON array (same order) where each element has:\n"
        '  "index": <int>,\n'
        '  "match_reasons": [<3 concise reasons why this role fits this user>],\n'
        '  "missing_skills": [<top 3 most important missing skills>]\n'
    )


def _apply_enrichments(
    top: list[JobMatchScore], enrichments: list[dict[str, Any]]
) -> None:
    index_map = {e.get("index"): e for e in enrichments if isinstance(e, dict)}
    for i, job in enumerate(top):
        enrichment = index_map.get(i, {})
        if reasons := enrichment.get("match_reasons"):
            job.match_reasons = [str(r) for r in reasons[:5]]
        if missing := enrichment.get("missing_skills"):
            job.missing_skills = [str(s) for s in missing[:5]]
