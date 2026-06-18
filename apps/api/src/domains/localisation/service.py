"""Localisation domain — service layer.

Generates country-aware career intelligence with the shared LLM client and
caches each report per user so repeat lookups are free. Reports are advisory:
the prompt forces an explicit confidence score and assumptions list, and forbids
inferring or acting on protected attributes.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.localisation.firestore_repository import (
    FirestoreLocalisationRepository,
)
from src.domains.localisation.schemas import (
    LocalisationReport,
    LocalisationReportSummary,
    report_slug,
)

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a global career-mobility and relocation expert advising \
a professional about working in a specific country in a specific role.

Return ONLY a valid JSON object — no markdown, no prose — with this exact schema:
{
  "summary": "2-3 sentence orientation for someone targeting this role in this country",
  "salary": {
    "currency": "ISO-like local currency code, e.g. EUR, USD, INR",
    "low": integer annual gross in local currency,
    "median": integer,
    "high": integer,
    "note": "one sentence on what drives the range / data caveats"
  },
  "cost_of_living": "one or two sentences on cost of living vs the salary",
  "visa_pathways": [
    {"name": "visa/permit name", "summary": "who qualifies and how", "difficulty": "easy|moderate|hard|unknown"}
  ],
  "language_requirements": "language expectations for this role and country",
  "hiring_culture": ["concise cultural note about hiring/interviewing", "..."],
  "networking_channels": ["specific community, event, or platform to use locally", "..."],
  "relocation_steps": ["ordered, concrete step", "..."],
  "confidence": 0.0,
  "assumptions": ["any assumption or data limitation behind this report", "..."]
}

Rules:
- Salaries are ANNUAL GROSS in the country's local currency. If unsure, widen the range and lower confidence.
- confidence (0.0-1.0) must honestly reflect how current/reliable your knowledge is for this country+role.
- Always populate assumptions with the real limits of this guidance (e.g. "rates vary by city", "visa rules change").
- Do NOT infer, request, or act on race, gender, age, nationality, disability, or any protected attribute.
- Be specific and practical; avoid generic filler. 3-6 items per list is ideal.
"""


class LocalisationService:
    def __init__(
        self,
        repo: FirestoreLocalisationRepository,
        llm: LlmJsonClient,
    ) -> None:
        self._repo = repo
        self._llm = llm

    async def get_report(
        self,
        user_id: str,
        country: str,
        role: str,
        *,
        refresh: bool = False,
    ) -> LocalisationReport:
        """Return a cached report for (country, role) or generate and cache one."""
        slug = report_slug(country, role)
        if not refresh:
            cached = await self._repo.get(slug, user_id)
            if cached is not None:
                return LocalisationReport.from_doc(cached)

        report = await self._generate(country, role)
        data = report.model_dump(exclude={"id", "generated_at"})
        data["generated_at"] = utcnow()

        existing = await self._repo.get(slug, user_id)
        if existing is not None:
            doc = await self._repo.update(slug, user_id, data)
        else:
            doc = await self._repo.create(user_id, data, doc_id=slug)
        logger.info(
            "localisation.report_generated",
            user_id=user_id,
            country=country,
            role=role,
            confidence=report.confidence,
        )
        return LocalisationReport.from_doc(doc or {"id": slug, **data})

    async def list_saved(
        self, user_id: str, limit: int = 30
    ) -> list[LocalisationReportSummary]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [LocalisationReportSummary.from_doc(d) for d in docs]

    async def delete(self, user_id: str, report_id: str) -> bool:
        return await self._repo.hard_delete(report_id, user_id)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _generate(self, country: str, role: str) -> LocalisationReport:
        user_msg = (
            f"Country: {country}\nTarget role: {role}\n"
            "Produce the localisation report as specified."
        )
        try:
            raw = await self._llm.complete_json(
                system=_SYSTEM_PROMPT, user=user_msg, max_tokens=2048
            )
        except ValueError:
            # Honest low-confidence fallback rather than a hard failure.
            return LocalisationReport(
                country=country,
                role=role,
                summary="We couldn't generate localisation guidance right now.",
                confidence=0.0,
                assumptions=["Report generation failed — please try again."],
            )
        if not isinstance(raw, dict):
            raw = {}
        raw["country"] = country
        raw["role"] = role
        try:
            return LocalisationReport.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("localisation.validate_failed", error=str(exc))
            return LocalisationReport(country=country, role=role, confidence=0.0)


async def get_localisation_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
) -> LocalisationService:
    return LocalisationService(FirestoreLocalisationRepository(db), llm)
