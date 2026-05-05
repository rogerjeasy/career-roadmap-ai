"""CVTailor — generates tailored CV snippets for high-match job listings.

For each high-match role, calls Claude to produce:
  - A one-line tailored professional summary
  - 3-5 achievement bullet points that mirror the job description language
  - ATS keyword list extracted from the posting

Falls back to structured placeholder snippets when the LLM is unavailable.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.contracts.tasks import UserProfileSnapshot
from agents.core.logging import get_logger
from agents.core.observability import OPP_TAILOR_DURATION, OPP_TAILOR_TOTAL
from agents.opportunity.models import CVTailoringSnippet, JobMatchScore

logger = get_logger(__name__)

_MAX_JOBS_TO_TAILOR = 5
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


class CVTailor:
    """Generates tailored CV snippets for high-match job listings.

    Parameters
    ----------
    llm:
        LangChain LLM. When ``None`` (e.g. in tests), returns structured
        fallback snippets instead.
    """

    def __init__(self, *, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm
        self._system_prompt = _load_prompt("cv_tailor_system.txt")

    async def tailor(
        self,
        high_match_jobs: list[JobMatchScore],
        profile: UserProfileSnapshot,
    ) -> list[CVTailoringSnippet]:
        """Generate tailored snippets for the top-N high-match jobs."""
        top_jobs = high_match_jobs[:_MAX_JOBS_TO_TAILOR]
        if not top_jobs:
            return []
        if self._llm is None:
            return [_fallback_snippet(job) for job in top_jobs]

        t0 = time.monotonic()
        try:
            user_prompt = _build_tailor_prompt(top_jobs, profile)
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

            snippets_raw: list[dict] = json.loads(raw)
            snippets = [
                _parse_snippet(job, s)
                for job, s in zip(top_jobs, snippets_raw)
            ]
            OPP_TAILOR_TOTAL.labels(status="llm").inc()
            return snippets
        except Exception as exc:
            logger.warning("opportunity.tailor.failed", error=str(exc))
            OPP_TAILOR_TOTAL.labels(status="fallback").inc()
            return [_fallback_snippet(job) for job in top_jobs]
        finally:
            OPP_TAILOR_DURATION.observe(time.monotonic() - t0)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_tailor_prompt(jobs: list[JobMatchScore], profile: UserProfileSnapshot) -> str:
    profile_section = (
        f"User:\n"
        f"- Current role: {profile.current_role or 'not specified'}\n"
        f"- Target role: {profile.target_role or 'not specified'}\n"
        f"- Skills: {', '.join(profile.skills[:25])}\n"
        f"- Goals: {'; '.join(profile.goals[:5])}\n"
    )
    jobs_section = "High-match job listings (JSON array):\n" + json.dumps(
        [
            {
                "index": i,
                "id": job.listing.id,
                "title": job.listing.title,
                "company": job.listing.company,
                "required_skills": job.listing.required_skills,
                "description": job.listing.description[:600],
                "skill_overlap": job.skill_overlap,
            }
            for i, job in enumerate(jobs)
        ],
        indent=2,
    )
    return (
        f"{profile_section}\n\n"
        f"{jobs_section}\n\n"
        "For each listing (same order) output a JSON array element with:\n"
        '  "summary_bullet": <one tailored professional summary sentence>,\n'
        '  "skill_highlights": [<3-5 achievement bullets, action verb first, quantified where possible>],\n'
        '  "keywords_to_include": [<5-8 ATS keywords from the job description>]\n'
    )


def _parse_snippet(job: JobMatchScore, raw: dict) -> CVTailoringSnippet:
    return CVTailoringSnippet(
        job_id=job.listing.id,
        job_title=job.listing.title,
        company=job.listing.company,
        summary_bullet=str(
            raw.get("summary_bullet", f"Results-driven professional targeting {job.listing.title}.")
        ),
        skill_highlights=list(raw.get("skill_highlights", [])),
        keywords_to_include=list(
            raw.get("keywords_to_include", job.listing.required_skills[:5])
        ),
    )


def _fallback_snippet(job: JobMatchScore) -> CVTailoringSnippet:
    overlap_str = ", ".join(job.skill_overlap[:3]) or "relevant technologies"
    return CVTailoringSnippet(
        job_id=job.listing.id,
        job_title=job.listing.title,
        company=job.listing.company,
        summary_bullet=(
            f"Experienced professional applying for {job.listing.title} "
            f"at {job.listing.company}."
        ),
        skill_highlights=[f"Proficient in {overlap_str}."],
        keywords_to_include=job.listing.required_skills[:5],
    )
