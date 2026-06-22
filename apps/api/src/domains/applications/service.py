"""Job Applications domain — service layer.

CRUD over tracked applications plus two LLM generators that tailor the user's
*real* CV (the text the cv domain cached in the session) and Evidence Vault to a
specific job description. Generated artefacts are stored back onto the
application document so they persist and can be revisited.

The pipeline keeps a full status ``timeline`` (every transition with a
timestamp), per-stage notes, and follow-up ``reminders`` — all stored inline on
the application document.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

if TYPE_CHECKING:
    from src.domains.push.service import PushService

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.applications.firestore_repository import FirestoreApplicationRepository
from src.domains.applications.schemas import (
    STAGES,
    ApplicationCreate,
    ApplicationOut,
    ApplicationSummary,
    ApplicationUpdate,
    ReminderCreate,
    normalize_status,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_TERMINAL = {"closed"}

_TAILOR_SYSTEM = """You are an expert résumé writer and ATS optimisation specialist. \
Tailor a candidate's existing CV to a specific job description. Use ONLY facts \
present in the candidate's CV and evidence — never invent employers, titles, \
metrics, or skills. If the candidate lacks something the job wants, list it under \
missing_keywords rather than fabricating it. Do not infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "summary": "a sharpened 2-3 sentence professional summary tailored to this role",
  "bullets": ["rewritten, impact-first résumé bullet aligned to the JD", "..."],
  "changes": [
    {"before": "the original bullet/phrase from the CV", "after": "your rewrite of it"}
  ],
  "matched_keywords": ["JD keyword the candidate genuinely has", "..."],
  "missing_keywords": ["important JD keyword the candidate lacks", "..."],
  "fit_score": integer 0-100 (honest fit of candidate to this JD),
  "advice": "1-2 sentences on how to close the biggest gap"
}
Rules: 4-8 bullets; be specific and quantified only where the CV supports it. In \
"changes", quote the candidate's ORIGINAL wording verbatim in "before" so a diff \
can be shown — one entry per bullet you rewrote.
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
        now = utcnow()
        if payload.status != "saved":
            data["applied_at"] = now
        data["timeline"] = [{"status": payload.status, "outcome": None, "note": "", "at": now}]
        doc = await self._repo.create(user_id, data)
        logger.info("application.created", user_id=user_id, app_id=doc["id"])
        return ApplicationOut.from_doc(doc)

    async def update(
        self, user_id: str, app_id: str, payload: ApplicationUpdate
    ) -> ApplicationOut:
        existing = await self._repo.get(app_id, user_id)
        if existing is None:
            raise NotFoundError("Application not found.")
        patch = payload.to_patch()
        if not patch:
            return ApplicationOut.from_doc(existing)

        new_status = patch.get("status")
        old_status, _ = normalize_status(existing.get("status"), existing.get("outcome"))
        if new_status and new_status != old_status:
            outcome = patch.get("outcome") if new_status == "closed" else None
            patch["outcome"] = outcome  # explicit None clears a prior outcome
            timeline = list(existing.get("timeline") or [])
            timeline.append(
                {"status": new_status, "outcome": outcome, "note": "", "at": utcnow()}
            )
            patch["timeline"] = timeline
            if new_status != "saved" and not existing.get("applied_at"):
                patch["applied_at"] = utcnow()

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
        due = 0
        now = datetime.now(timezone.utc)
        for d in docs:
            status, _ = normalize_status(d.get("status"), d.get("outcome"))
            by_status[status] = by_status.get(status, 0) + 1
            for r in d.get("reminders") or []:
                if isinstance(r, dict) and not r.get("done") and _is_due(r.get("due_at"), now):
                    due += 1
        active = sum(c for s, c in by_status.items() if s not in _TERMINAL)
        return ApplicationSummary(
            total=len(docs), by_status=by_status, active=active, due_reminders=due
        )

    # ── Per-stage notes ────────────────────────────────────────────────────────

    async def set_stage_note(
        self, user_id: str, app_id: str, stage: str, note: str
    ) -> ApplicationOut:
        if stage not in STAGES:
            raise ValidationError(f"Unknown stage {stage!r}.")
        doc = await self._require(user_id, app_id)
        stage_notes = dict(doc.get("stage_notes") or {})
        if note.strip():
            stage_notes[stage] = note
        else:
            stage_notes.pop(stage, None)
        updated = await self._repo.update(app_id, user_id, {"stage_notes": stage_notes})
        return ApplicationOut.from_doc(updated or doc)

    # ── Reminders ───────────────────────────────────────────────────────────────

    async def add_reminder(
        self, user_id: str, app_id: str, payload: ReminderCreate
    ) -> ApplicationOut:
        doc = await self._require(user_id, app_id)
        reminders = list(doc.get("reminders") or [])
        reminders.append(
            {
                "id": str(uuid4()),
                "title": payload.title,
                "due_at": payload.due_at,
                "done": False,
                "created_at": utcnow(),
            }
        )
        updated = await self._repo.update(app_id, user_id, {"reminders": reminders})
        logger.info("application.reminder_added", user_id=user_id, app_id=app_id)
        return ApplicationOut.from_doc(updated or doc)

    async def set_reminder_done(
        self, user_id: str, app_id: str, reminder_id: str, done: bool
    ) -> ApplicationOut:
        doc = await self._require(user_id, app_id)
        reminders = list(doc.get("reminders") or [])
        found = False
        for r in reminders:
            if isinstance(r, dict) and r.get("id") == reminder_id:
                r["done"] = done
                found = True
        if not found:
            raise NotFoundError("Reminder not found.")
        updated = await self._repo.update(app_id, user_id, {"reminders": reminders})
        return ApplicationOut.from_doc(updated or doc)

    async def delete_reminder(
        self, user_id: str, app_id: str, reminder_id: str
    ) -> ApplicationOut:
        doc = await self._require(user_id, app_id)
        reminders = [
            r
            for r in (doc.get("reminders") or [])
            if not (isinstance(r, dict) and r.get("id") == reminder_id)
        ]
        updated = await self._repo.update(app_id, user_id, {"reminders": reminders})
        return ApplicationOut.from_doc(updated or doc)

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
            raw = await self._llm.complete_json(system=_TAILOR_SYSTEM, user=prompt, max_tokens=2560)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        changes = [
            {"before": c.get("before", ""), "after": c.get("after", "")}
            for c in (raw.get("changes") or [])
            if isinstance(c, dict) and (c.get("before") or c.get("after"))
        ]
        tailored = {
            "summary": raw.get("summary", ""),
            "bullets": raw.get("bullets", []),
            "changes": changes,
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


def _is_due(due_at: datetime | None, now: datetime) -> bool:
    if not isinstance(due_at, datetime):
        return False
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    return due_at <= now


async def fire_due_reminders(
    repo: FirestoreApplicationRepository,
    push: "PushService",
    now: datetime | None = None,
    limit: int = 2000,
) -> int:
    """Push every reminder that is now due, exactly once.

    Scans all applications, sends a web-push for each undone reminder whose
    ``due_at`` has passed, and stamps it ``fired_at`` so a later sweep never
    re-sends it. Returns the number of notifications dispatched. Designed to be
    driven by a Celery-beat tick — see ``src.tasks.reminder_tasks``.
    """
    moment = now or datetime.now(timezone.utc)
    docs = await repo.iter_all(limit=limit)
    fired = 0
    for doc in docs:
        user_id = doc.get("user_id")
        if not user_id:
            continue
        reminders = doc.get("reminders") or []
        due_titles: list[str] = []
        for r in reminders:
            if not isinstance(r, dict) or r.get("done") or r.get("fired_at"):
                continue
            if _is_due(r.get("due_at"), moment):
                r["fired_at"] = moment
                due_titles.append(str(r.get("title", "")).strip() or "Follow-up")
        if not due_titles:
            continue
        label = " at ".join(p for p in (doc.get("role", ""), doc.get("company", "")) if p)
        for title in due_titles:
            await push.send_to_user(
                user_id,
                title="Reminder due",
                body=f"{title} — {label}" if label else title,
                url="/applications",
            )
            fired += 1
        await repo.update(doc["id"], user_id, {"reminders": reminders})
    if fired:
        logger.info("application.reminders_fired", count=fired)
    return fired


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
