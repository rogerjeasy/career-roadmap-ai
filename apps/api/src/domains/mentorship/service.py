"""Mentorship — service layer.

Coordinates mentor profiles, matched discovery, the request→accept session
lifecycle (human-approval gate), and the member-contributed insider-conversation
library. Mentor discovery ranks active mentors by how well their expertise
overlaps the mentee's real target role and skills from the session profile.
"""
from __future__ import annotations

import re

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.mentorship.firestore_repository import FirestoreMentorshipRepository, _utcnow
from src.domains.mentorship.schemas import (
    CaseStudyCreate,
    CaseStudyOut,
    MentorProfileOut,
    MentorProfileUpsert,
    MentorSessionOut,
    SessionRequest,
    SessionRespond,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) > 2}


class MentorshipService:
    def __init__(self, repo: FirestoreMentorshipRepository, sessions: SessionManager) -> None:
        self._repo = repo
        self._sessions = sessions

    # ── Mentor profile ────────────────────────────────────────────────────────

    async def get_my_profile(self, user_id: str) -> MentorProfileOut | None:
        doc = await self._repo.get_profile(user_id)
        return MentorProfileOut.from_doc(doc) if doc else None

    async def upsert_profile(
        self, user_id: str, name: str, payload: MentorProfileUpsert
    ) -> MentorProfileOut:
        doc = await self._repo.upsert_profile(user_id, name, payload.model_dump())
        logger.info("mentorship.profile_upserted", user_id=user_id)
        return MentorProfileOut.from_doc(doc)

    async def deactivate_profile(self, user_id: str) -> None:
        await self._repo.deactivate_profile(user_id)

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def discover_mentors(self, user_id: str) -> list[MentorProfileOut]:
        interest = await self._interest_tokens(user_id)
        docs = await self._repo.list_active_profiles(limit=100)
        out: list[MentorProfileOut] = []
        for d in docs:
            if d.get("user_id") == user_id:
                continue
            mentor = MentorProfileOut.from_doc(d)
            score, reason = self._match(interest, d)
            mentor.match_score = score
            mentor.match_reason = reason
            out.append(mentor)
        out.sort(key=lambda m: m.match_score, reverse=True)
        return out

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def request_session(
        self, user_id: str, user_name: str, payload: SessionRequest
    ) -> MentorSessionOut:
        if payload.mentor_id == user_id:
            raise ValidationError("You cannot request a session with yourself.")
        mentor = await self._repo.get_profile(payload.mentor_id)
        if mentor is None or not mentor.get("is_active", False):
            raise NotFoundError("That mentor is not available.")
        doc = await self._repo.create_session(
            {
                "mentor_id": payload.mentor_id,
                "mentor_name": mentor.get("name", "A mentor"),
                "mentee_id": user_id,
                "mentee_name": user_name,
                "topic": payload.topic,
                "message": payload.message,
            }
        )
        logger.info(
            "mentorship.session_requested", mentor_id=payload.mentor_id, mentee_id=user_id
        )
        return MentorSessionOut.from_doc(doc, viewer_id=user_id)

    async def list_my_sessions(self, user_id: str) -> list[MentorSessionOut]:
        as_mentee = await self._repo.list_sessions_for(user_id, "mentee_id")
        as_mentor = await self._repo.list_sessions_for(user_id, "mentor_id")
        merged = {d["id"]: d for d in (*as_mentee, *as_mentor)}
        out = [MentorSessionOut.from_doc(d, viewer_id=user_id) for d in merged.values()]
        out.sort(key=lambda s: s.created_at or _utcnow(), reverse=True)
        return out

    async def respond_session(
        self, user_id: str, session_id: str, payload: SessionRespond
    ) -> MentorSessionOut:
        doc = await self._repo.get_session(session_id)
        if doc is None:
            raise NotFoundError("Session not found.")
        if doc.get("mentor_id") != user_id:
            raise AuthorizationError("Only the mentor can respond to this request.")
        if doc.get("status") != "requested":
            raise ConflictError("This request has already been answered.")
        updated = await self._repo.update_session(
            session_id,
            {"status": payload.decision, "reply": payload.reply, "responded_at": _utcnow()},
        )
        logger.info(
            "mentorship.session_responded",
            session_id=session_id,
            decision=payload.decision,
        )
        return MentorSessionOut.from_doc(updated or doc, viewer_id=user_id)

    async def complete_session(self, user_id: str, session_id: str) -> MentorSessionOut:
        doc = await self._repo.get_session(session_id)
        if doc is None:
            raise NotFoundError("Session not found.")
        if user_id not in (doc.get("mentor_id"), doc.get("mentee_id")):
            raise AuthorizationError("You are not part of this session.")
        if doc.get("status") != "accepted":
            raise ConflictError("Only an accepted session can be completed.")
        updated = await self._repo.update_session(session_id, {"status": "completed"})
        return MentorSessionOut.from_doc(updated or doc, viewer_id=user_id)

    # ── Insider conversations ─────────────────────────────────────────────────

    async def list_case_studies(self, user_id: str) -> list[CaseStudyOut]:
        docs = await self._repo.list_cases(limit=100)
        return [CaseStudyOut.from_doc(d, viewer_id=user_id) for d in docs]

    async def create_case_study(
        self, user_id: str, user_name: str, payload: CaseStudyCreate
    ) -> CaseStudyOut:
        doc = await self._repo.create_case(user_id, user_name, payload.model_dump())
        logger.info("mentorship.case_study_created", user_id=user_id, case_id=doc["id"])
        return CaseStudyOut.from_doc(doc, viewer_id=user_id)

    async def delete_case_study(self, user_id: str, case_id: str) -> None:
        doc = await self._repo.get_case(case_id)
        if doc is None or doc.get("deleted_at") is not None:
            raise NotFoundError("Case study not found.")
        if doc.get("author_id") != user_id:
            raise AuthorizationError("You can only delete your own case study.")
        await self._repo.soft_delete_case(case_id)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _interest_tokens(self, user_id: str) -> set[str]:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return set()
        text = " ".join(filter(None, [profile.target_role, *(profile.skills or [])]))
        return _tokens(text)

    @staticmethod
    def _match(interest: set[str], doc: dict) -> tuple[int, str]:
        expertise = doc.get("expertise") or []
        exp_tokens = _tokens(" ".join(expertise) + " " + doc.get("headline", ""))
        if not interest:
            return 0, "Add a target role to see how this mentor fits your goals."
        if not exp_tokens:
            return 0, "General mentorship."
        overlap = interest & exp_tokens
        score = round(100 * len(overlap) / max(1, len(interest)))
        if overlap:
            shared = ", ".join(sorted(overlap)[:3])
            return score, f"Expertise in {shared}, which maps to your goal."
        return score, "Outside your current focus, but may offer a fresh perspective."


async def get_mentorship_service(
    db: AsyncClient = Depends(get_firestore_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> MentorshipService:
    return MentorshipService(FirestoreMentorshipRepository(db), sessions)
