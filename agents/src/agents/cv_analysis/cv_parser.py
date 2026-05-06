"""CVParser — LLM-based structured extraction from raw CV / résumé text.

Converts free-form CV text into a typed ``ParsedCV`` dataclass via a single
structured LLM call. Falls back to a minimal empty ``ParsedCV`` on failure.

Design:
- Stateless: holds only the LLM client.
- Observable: OTel span + Prometheus counters on every parse call.
- Resilient: retries up to 3 times with exponential back-off.
- Testable: inject a mock ``llm`` to bypass real API calls.
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
from agents.core.observability import CV_PARSE_DURATION, CV_PARSE_TOTAL, get_tracer
from agents.cv_analysis.models import EducationEntry, ExperienceEntry, ParsedCV, ProjectEntry

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.cv_parser")

# CV text is truncated at 12 000 chars to stay within token budgets.
_MAX_CV_CHARS = 12_000

_SYSTEM_PROMPT = """\
You are a CV/résumé parser. Extract structured information from the given CV text.
Respond with ONLY valid JSON — no markdown fences, no prose.

Return this exact structure:
{
  "full_name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "summary": "string or null",
  "total_experience_months": integer or null,
  "raw_skills": ["list of skill strings from any section"],
  "certifications": ["certification names, e.g. AWS Solutions Architect 2023"],
  "languages": ["human languages spoken, NOT programming languages"],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "YYYY-MM or free text or null",
      "end_date": "YYYY-MM, present, or null",
      "duration_months": integer or null,
      "responsibilities": ["list of responsibility strings"],
      "impact_statements": ["quantified achievements, e.g. reduced latency by 40%"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string or null",
      "field_of_study": "string or null",
      "graduation_year": integer or null,
      "gpa": float or null
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string",
      "technologies": ["tech strings used in this project"],
      "impact": "string or null"
    }
  ]
}

Extraction rules:
- Extract ONLY information present in the text; never invent values.
- impact_statements: prefer quantified results (numbers, percentages, scale).
- total_experience_months: sum across non-overlapping roles; null if unclear.
- raw_skills: collect from skills section, experience descriptions, and projects.
- certifications: include the year if visible in the text.
- languages: spoken/written human languages only — not programming languages.
"""


class CVParser:
    """Parse raw CV text into a structured ``ParsedCV``.

    Inject a custom ``llm`` in tests to avoid real Anthropic API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=4096,
            temperature=0.0,
        )

    async def parse(
        self,
        raw_text: str,
        *,
        correlation_id: str = "",
    ) -> ParsedCV:
        """Parse ``raw_text`` into a structured ``ParsedCV``.

        Returns a minimal ``ParsedCV`` (not an error) when the text is empty
        or the LLM call fails after all retry attempts.
        """
        if not raw_text.strip():
            return ParsedCV(raw_text=raw_text)

        with _tracer.start_as_current_span("cv.parse") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("text_length", len(raw_text))
            t0 = time.monotonic()

            try:
                raw = await self._call_llm(raw_text)
                result = _build_parsed_cv(raw, raw_text)

                duration = time.monotonic() - t0
                CV_PARSE_DURATION.observe(duration)
                CV_PARSE_TOTAL.labels(status="success").inc()

                span.set_attribute("experience_entries", len(result.experience))
                span.set_attribute("education_entries", len(result.education))
                span.set_attribute("raw_skills_count", len(result.raw_skills))
                span.set_attribute("duration_ms", int(duration * 1000))
                span.set_status(Status(StatusCode.OK))

                logger.info(
                    "cv.parsed",
                    experience_entries=len(result.experience),
                    education_entries=len(result.education),
                    raw_skills=len(result.raw_skills),
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return result

            except Exception as exc:
                duration = time.monotonic() - t0
                CV_PARSE_DURATION.observe(duration)
                CV_PARSE_TOTAL.labels(status="fallback").inc()

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

                logger.warning(
                    "cv.parse_failed",
                    error=str(exc),
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return ParsedCV(raw_text=raw_text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _call_llm(self, text: str) -> dict[str, Any]:
        truncated = text[:_MAX_CV_CHARS]
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=truncated),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return raw


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_parsed_cv(raw: dict[str, Any], raw_text: str) -> ParsedCV:
    """Convert raw LLM JSON into a typed ``ParsedCV``."""
    experience = [
        ExperienceEntry(
            company=str(e.get("company", "")),
            title=str(e.get("title", "")),
            start_date=e.get("start_date"),
            end_date=e.get("end_date"),
            duration_months=_safe_int(e.get("duration_months")),
            responsibilities=[str(r) for r in e.get("responsibilities", []) if r],
            impact_statements=[str(i) for i in e.get("impact_statements", []) if i],
        )
        for e in raw.get("experience", [])
        if e.get("company") or e.get("title")
    ]

    education = [
        EducationEntry(
            institution=str(e.get("institution", "")),
            degree=e.get("degree"),
            field_of_study=e.get("field_of_study"),
            graduation_year=_safe_int(e.get("graduation_year")),
            gpa=_safe_float(e.get("gpa")),
        )
        for e in raw.get("education", [])
        if e.get("institution")
    ]

    projects = [
        ProjectEntry(
            name=str(p.get("name", "")),
            description=str(p.get("description", "")),
            technologies=[str(t) for t in p.get("technologies", []) if t],
            impact=p.get("impact"),
        )
        for p in raw.get("projects", [])
        if p.get("name")
    ]

    return ParsedCV(
        raw_text=raw_text,
        full_name=raw.get("full_name"),
        email=raw.get("email"),
        phone=raw.get("phone"),
        location=raw.get("location"),
        summary=raw.get("summary"),
        experience=experience,
        education=education,
        projects=projects,
        raw_skills=[str(s) for s in raw.get("raw_skills", []) if s],
        certifications=[str(c) for c in raw.get("certifications", []) if c],
        languages=[str(lang) for lang in raw.get("languages", []) if lang],
        total_experience_months=_safe_int(raw.get("total_experience_months")),
    )


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
