"""Career Twin — service layer.

Manages the persona and runs the daily check-in loop. Today's check-in is created
lazily: the first time it's requested for a given UTC date, the Twin generates an
opening grounded in the user's real profile + roadmap snapshot. The user's reply
triggers the Twin's response. Generation degrades gracefully to a static prompt
if the LLM is unavailable, so the check-in always works.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import ConflictError, NotFoundError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.career_twin.firestore_repository import (
    FirestoreTwinCheckinRepository,
    FirestoreTwinPersonaRepository,
)
from src.domains.career_twin.schemas import (
    DailyCheckinOut,
    TwinPersonaOut,
    TwinPersonaUpsert,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class CareerTwinService:
    def __init__(
        self,
        persona_repo: FirestoreTwinPersonaRepository,
        checkin_repo: FirestoreTwinCheckinRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._persona = persona_repo
        self._checkins = checkin_repo
        self._llm = llm
        self._sessions = sessions

    # ── Persona ───────────────────────────────────────────────────────────────

    async def get_persona(self, user_id: str) -> TwinPersonaOut:
        doc = await self._persona.get(user_id, user_id)
        return TwinPersonaOut.from_doc(doc)

    async def upsert_persona(
        self, user_id: str, payload: TwinPersonaUpsert
    ) -> TwinPersonaOut:
        existing = await self._persona.get(user_id, user_id)
        if existing is None:
            doc = await self._persona.create(user_id, payload.model_dump(), doc_id=user_id)
        else:
            doc = await self._persona.update(user_id, user_id, payload.model_dump())
        logger.info("career_twin.persona_saved", user_id=user_id)
        return TwinPersonaOut.from_doc(doc)

    # ── Daily check-in ────────────────────────────────────────────────────────

    async def today(self, user_id: str) -> DailyCheckinOut:
        date = _today()
        existing = await self._find_for_date(user_id, date)
        if existing is not None:
            return DailyCheckinOut.from_doc(existing)

        persona = await self.get_persona(user_id)
        opening = await self._generate_opening(user_id, persona)
        doc = await self._checkins.create(
            user_id,
            {
                "date": date,
                "greeting": opening["greeting"],
                "prompt": opening["prompt"],
                "focus_suggestion": opening["focus_suggestion"],
                "user_reply": "",
                "twin_response": "",
                "mood": None,
                "status": "open",
            },
        )
        return DailyCheckinOut.from_doc(doc)

    async def reply(
        self, user_id: str, checkin_id: str, reply: str, mood: int | None
    ) -> DailyCheckinOut:
        doc = await self._checkins.get(checkin_id, user_id)
        if doc is None:
            raise NotFoundError("Check-in not found.")
        if doc.get("status") == "answered":
            raise ConflictError("You've already replied to this check-in.")
        persona = await self.get_persona(user_id)
        response = await self._generate_response(user_id, persona, doc, reply)
        updated = await self._checkins.update(
            checkin_id,
            user_id,
            {
                "user_reply": reply,
                "mood": mood,
                "twin_response": response,
                "status": "answered",
            },
        )
        logger.info("career_twin.checkin_answered", user_id=user_id, checkin_id=checkin_id)
        return DailyCheckinOut.from_doc(updated or doc)

    async def history(self, user_id: str, limit: int = 60) -> list[DailyCheckinOut]:
        docs = await self._checkins.list_for_user(user_id, limit=limit)
        return [DailyCheckinOut.from_doc(d) for d in docs]

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _find_for_date(self, user_id: str, date: str) -> dict | None:
        docs = await self._checkins.list_for_user(user_id, limit=10)
        for d in docs:
            if d.get("date") == date:
                return d
        return None

    async def _context(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        plan = session.plan_context if session else None
        parts: list[str] = []
        if profile is not None:
            if profile.target_role:
                parts.append(f"Target role: {profile.target_role}")
            if profile.current_role:
                parts.append(f"Current role: {profile.current_role}")
            if profile.goals:
                parts.append("Goals: " + "; ".join(profile.goals[:5]))
        if plan is not None and plan.snapshot:
            summary = plan.snapshot.get("summary")
            if isinstance(summary, str) and summary:
                parts.append("Roadmap: " + summary[:400])
        return "\n".join(parts) or "No profile context yet."

    @staticmethod
    def _voice_note(persona: TwinPersonaOut) -> str:
        return (
            f"You are '{persona.name}', the user's career twin. Speak in a "
            f"{persona.voice} voice."
            + (f" Their stated focus: {persona.focus}." if persona.focus else "")
        )

    async def _generate_opening(self, user_id: str, persona: TwinPersonaOut) -> dict:
        context = await self._context(user_id)
        system = (
            self._voice_note(persona)
            + " Open today's daily check-in. Be brief and human. "
            "Do not infer protected attributes.\n\n"
            "Return ONLY JSON: {\"greeting\": \"one warm line\", "
            "\"prompt\": \"one focused question for today\", "
            "\"focus_suggestion\": \"one concrete thing worth doing today\"}"
        )
        try:
            raw = await self._llm.complete_json(system=system, user=context, max_tokens=512)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "greeting": str(raw.get("greeting") or f"Hi — {persona.name} here."),
            "prompt": str(raw.get("prompt") or "What's the one thing you want to move forward today?"),
            "focus_suggestion": str(raw.get("focus_suggestion") or ""),
        }

    async def _generate_response(
        self, user_id: str, persona: TwinPersonaOut, checkin: dict, reply: str
    ) -> str:
        context = await self._context(user_id)
        system = (
            self._voice_note(persona)
            + " The user just answered your daily check-in. Respond in 2-4 sentences: "
            "acknowledge, give one honest, specific nudge, and close warmly. Never "
            "invent progress. Do not infer protected attributes.\n\n"
            "Return ONLY JSON: {\"response\": \"your reply\"}"
        )
        user_prompt = (
            f"CONTEXT:\n{context}\n\n"
            f"Today's prompt was: {checkin.get('prompt', '')}\n"
            f"User replied: {reply}"
        )
        try:
            raw = await self._llm.complete_json(system=system, user=user_prompt, max_tokens=512)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return str(raw.get("response") or "Thanks for checking in — keep the momentum going.")


async def get_career_twin_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> CareerTwinService:
    return CareerTwinService(
        FirestoreTwinPersonaRepository(db),
        FirestoreTwinCheckinRepository(db),
        llm,
        sessions,
    )
