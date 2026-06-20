"""Job Applications domain — service layer.

CRUD over tracked applications plus two LLM generators that tailor the user's
*real* CV (the text the cv domain cached in the session) and Evidence Vault to a
specific job description. Generated artefacts are stored back onto the
application document so they persist and can be revisited.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.applications.firestore_repository import FirestoreApplicationRepository
from src.domains.applications.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationSummary,
    ApplicationUpdate,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_TERMINAL = {"rejected", "accepted", "withdrawn"}

_TAILOR_SYSTEM = """You are an expert résumé writer and ATS optimisation specialist. \
Tailor a candidate's existing CV to a specific job description. Use ONLY facts \
present in the candidate's CV and evidence — never invent employers, titles, \
metrics, or skills. If the candidate lacks something the job wants, list it under \
missing_keywords rather than fabricating it. Do not infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "summary": "a sharpened 2-3 sentence professional summary tailored to this role",
  "bullets": ["rewritten, impact-first résumé bullet aligned to the JD", "..."],
  "matched_keywords": ["JD keyword the candidate genuinely has", "..."],
  "missing_keywords": ["important JD keyword the candidate lacks", "..."],
  "fit_score": integer 0-100 (honest fit of candidate to this JD),
  "advice": "1-2 sentences on how to close the biggest gap"
}
Rules: 4-8 bullets; be specific and quantified only where the CV supports it.
"""

_COVER_SYSTEM = """You are an expert career writer. Write a tailored cover letter for \
the candidate and role below, grounded only in the candidate's real CV and \
evidence — never invent facts. Keep it to 3-4 tight paragraphs, specific and \
free of clichés. Do not reference or infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{ "content": "the full cover letter text" }
"""


class ApplicationService:
    def __init__(
        self,
        repo: FirestoreApplicationRepository,
        evidence: FirestoreCrudRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._evidence = evidence
        self._llm = llm
        self._sessions = sessions

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def list(self, user_id: str) -> list[ApplicationOut]:
        docs = await self._repo.list_for_user(user_id, limit=200)
        return [ApplicationOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, app_id: str) -> ApplicationOut:
        doc = await self._repo.get(app_id, user_id)
        if doc is None:
            raise NotFoundError("Application not found.")
        return ApplicationOut.from_doc(doc)

    async def create(self, user_id: str, payload: ApplicationCreate) -> ApplicationOut:
        data = payload.model_dump()
        if payload.status != "saved":
            data["applied_at"] = utcnow()
        doc = await self._repo.create(user_id, data)
        logger.info("application.created", user_id=user_id, app_id=doc["id"])
        return ApplicationOut.from_doc(doc)

    async def update(
        self, user_id: str, app_id: str, payload: ApplicationUpdate
    ) -> ApplicationOut:
        patch = payload.to_patch()
        if not patch:
            return await self.get(user_id, app_id)
        doc = await self._repo.update(app_id, user_id, patch)
        if doc is None:
            raise NotFoundError("Application not found.")
        return ApplicationOut.from_doc(doc)

    async def delete(self, user_id: str, app_id: str) -> None:
        removed = await self._repo.soft_delete(app_id, user_id)
        if not removed:
            raise NotFoundError("Application not found.")

    async def summary(self, user_id: str) -> ApplicationSummary:
        docs = await self._repo.list_for_user(user_id, limit=500)
        by_status: dict[str, int] = {}
        for d in docs:
            s = d.get("status", "saved")
            by_status[s] = by_status.get(s, 0) + 1
        active = sum(c for s, c in by_status.items() if s not in _TERMINAL)
        return ApplicationSummary(total=len(docs), by_status=by_status, active=active)

    # ── LLM generation ────────────────────────────────────────────────────────

    async def tailor_cv(self, user_id: str, app_id: str) -> ApplicationOut:
        doc = await self._require(user_id, app_id)
        cv_text = await self._cv_text(user_id)
        if not cv_text:
            raise ValidationError(
                "Upload or import a CV first — tailoring rewrites your real CV."
            )
        evidence = await self._evidence_lines(user_id)
        prompt = (
            f"JOB: {doc.get('role', '')} at {doc.get('company', '')}\n\n"
            f"JOB DESCRIPTION:\n{(doc.get('job_description') or '(none provided)')[:12000]}\n\n"
            f"CANDIDATE CV:\n{cv_text[:12000]}\n\n"
            f"EVIDENCE HIGHLIGHTS:\n{evidence or '(none)'}\n\n"
            "Tailor the CV to this job per the schema."
        )
        try:
            raw = await self._llm.complete_json(system=_TAILOR_SYSTEM, user=prompt, max_tokens=2048)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        tailored = {
            "summary": raw.get("summary", ""),
            "bullets": raw.get("bullets", []),
            "matched_keywords": raw.get("matched_keywords", []),
            "missing_keywords": raw.get("missing_keywords", []),
            "fit_score": raw.get("fit_score", 0),
            "advice": raw.get("advice", ""),
            "generated_at": utcnow(),
        }
        updated = await self._repo.update(app_id, user_id, {"tailored_cv": tailored})
        logger.info("application.cv_tailored", user_id=user_id, app_id=app_id)
        return ApplicationOut.from_doc(updated or doc)

    async def cover_letter(self, user_id: str, app_id: str) -> ApplicationOut:
        doc = await self._require(user_id, app_id)
        cv_text = await self._cv_text(user_id)
        if not cv_text:
            raise ValidationError(
                "Upload or import a CV first — the cover letter draws on your real CV."
            )
        evidence = await self._evidence_lines(user_id)
        prompt = (
            f"ROLE: {doc.get('role', '')} at {doc.get('company', '')}\n"
            f"LOCATION: {doc.get('location', '')}\n\n"
            f"JOB DESCRIPTION:\n{(doc.get('job_description') or '(none provided)')[:10000]}\n\n"
            f"CANDIDATE CV:\n{cv_text[:10000]}\n\n"
            f"EVIDENCE HIGHLIGHTS:\n{evidence or '(none)'}\n\n"
            "Write the cover letter per the schema."
        )
        try:
            raw = await self._llm.complete_json(system=_COVER_SYSTEM, user=prompt, max_tokens=1536)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        letter = {"content": raw.get("content", ""), "generated_at": utcnow()}
        updated = await self._repo.update(app_id, user_id, {"cover_letter": letter})
        logger.info("application.cover_letter_generated", user_id=user_id, app_id=app_id)
        return ApplicationOut.from_doc(updated or doc)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _require(self, user_id: str, app_id: str) -> dict:
        doc = await self._repo.get(app_id, user_id)
        if doc is None:
            raise NotFoundError("Application not found.")
        return doc

    async def _cv_text(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return ""
        text = profile.additional.get("cv_text")
        return text if isinstance(text, str) else ""

    async def _evidence_lines(self, user_id: str) -> str:
        docs = await self._evidence.list_for_user(user_id, limit=15)
        lines = [
            f"- {d.get('title', '')}: {d.get('description', '')}".strip()
            for d in docs
            if d.get("title")
        ]
        return "\n".join(lines)


async def get_application_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> ApplicationService:
    return ApplicationService(
        FirestoreApplicationRepository(db),
        FirestoreCrudRepository(db, "evidence"),
        llm,
        sessions,
    )
