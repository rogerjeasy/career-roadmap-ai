"""Accountability Cohorts — service layer.

Owns the membership lifecycle (create / discover / join / leave), gates every
read of a shared cohort on membership, and ranks the discover feed by how well a
cohort's focus overlaps the user's real target role and goals (from the session
profile). Check-ins are visible to all members of a cohort and only postable by
members.
"""
from __future__ import annotations

import re

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.cohorts.firestore_repository import FirestoreCohortRepository, _utcnow
from src.domains.cohorts.schemas import (
    CheckinCreate,
    CheckinOut,
    CohortCreate,
    CohortDashboard,
    CohortOut,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_STOPWORDS = {"the", "a", "an", "to", "and", "of", "in", "for", "as", "my", "into", "at"}


def _tokens(text: str) -> set[str]:
    return {
        w
        for w in re.split(r"[^a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


class CohortService:
    def __init__(self, repo: FirestoreCohortRepository, sessions: SessionManager) -> None:
        self._repo = repo
        self._sessions = sessions

    # ── Membership lifecycle ──────────────────────────────────────────────────

    async def create(self, user_id: str, user_name: str, payload: CohortCreate) -> CohortOut:
        doc = await self._repo.create(user_id, user_name, payload.model_dump())
        return CohortOut.from_doc(doc, viewer_id=user_id)

    async def list_mine(self, user_id: str) -> list[CohortOut]:
        docs = await self._repo.list_for_member(user_id)
        return [CohortOut.from_doc(d, viewer_id=user_id) for d in docs]

    async def discover(self, user_id: str) -> list[CohortOut]:
        """Open cohorts the user hasn't joined, ranked by focus/goal overlap."""
        interest = await self._interest_tokens(user_id)
        docs = await self._repo.list_open(limit=100)
        out: list[CohortOut] = []
        for d in docs:
            member_ids = d.get("member_ids") or []
            if user_id in member_ids:
                continue
            if len(member_ids) >= int(d.get("capacity", 6) or 6):
                continue
            cohort = CohortOut.from_doc(d, viewer_id=user_id)
            score, reason = self._match(interest, d)
            cohort.match_score = score
            cohort.match_reason = reason
            out.append(cohort)
        out.sort(key=lambda c: c.match_score, reverse=True)
        return out

    async def join(self, user_id: str, user_name: str, cohort_id: str) -> CohortOut:
        doc = await self._require_cohort(cohort_id)
        member_ids = list(doc.get("member_ids") or [])
        if user_id in member_ids:
            return CohortOut.from_doc(doc, viewer_id=user_id)
        if len(member_ids) >= int(doc.get("capacity", 6) or 6):
            raise ConflictError("This cohort is already full.")
        members = list(doc.get("members") or [])
        members.append({"uid": user_id, "name": user_name, "joined_at": _utcnow()})
        member_ids.append(user_id)
        status = "full" if len(member_ids) >= int(doc.get("capacity", 6) or 6) else "open"
        updated = await self._repo.update(
            cohort_id, {"members": members, "member_ids": member_ids, "status": status}
        )
        logger.info("cohort.joined", cohort_id=cohort_id, user_id=user_id)
        return CohortOut.from_doc(updated or doc, viewer_id=user_id)

    async def leave(self, user_id: str, cohort_id: str) -> None:
        doc = await self._require_cohort(cohort_id)
        member_ids = [m for m in (doc.get("member_ids") or []) if m != user_id]
        members = [m for m in (doc.get("members") or []) if m.get("uid") != user_id]
        if not member_ids:
            # Last member out — archive the empty cohort.
            await self._repo.soft_delete(cohort_id)
            return
        status = "open" if len(member_ids) < int(doc.get("capacity", 6) or 6) else "full"
        await self._repo.update(
            cohort_id, {"members": members, "member_ids": member_ids, "status": status}
        )
        logger.info("cohort.left", cohort_id=cohort_id, user_id=user_id)

    # ── Dashboard & check-ins ─────────────────────────────────────────────────

    async def dashboard(self, user_id: str, cohort_id: str) -> CohortDashboard:
        doc = await self._require_membership(user_id, cohort_id)
        checkins = await self._repo.list_checkins(cohort_id, limit=50)
        return CohortDashboard(
            cohort=CohortOut.from_doc(doc, viewer_id=user_id),
            checkins=[CheckinOut.from_doc(c) for c in checkins],
        )

    async def post_checkin(
        self, user_id: str, user_name: str, cohort_id: str, payload: CheckinCreate
    ) -> CheckinOut:
        await self._require_membership(user_id, cohort_id)
        doc = await self._repo.add_checkin(
            cohort_id, user_id, user_name, payload.model_dump()
        )
        logger.info("cohort.checkin_posted", cohort_id=cohort_id, user_id=user_id)
        return CheckinOut.from_doc(doc)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _require_cohort(self, cohort_id: str) -> dict:
        doc = await self._repo.get(cohort_id)
        if doc is None:
            raise NotFoundError("Cohort not found.")
        return doc

    async def _require_membership(self, user_id: str, cohort_id: str) -> dict:
        doc = await self._require_cohort(cohort_id)
        if user_id not in (doc.get("member_ids") or []):
            raise AuthorizationError("You are not a member of this cohort.")
        return doc

    async def _interest_tokens(self, user_id: str) -> set[str]:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return set()
        text = " ".join(
            filter(None, [profile.target_role, profile.current_role, *(profile.goals or [])])
        )
        return _tokens(text)

    @staticmethod
    def _match(interest: set[str], doc: dict) -> tuple[int, str]:
        if not interest:
            return 0, "Sign in with a target role to see how well this fits your goals."
        focus_tokens = _tokens(f"{doc.get('focus', '')} {doc.get('name', '')}")
        overlap = interest & focus_tokens
        if not focus_tokens:
            return 0, "Open to all goals."
        score = round(100 * len(overlap) / max(1, len(focus_tokens)))
        if overlap:
            shared = ", ".join(sorted(overlap)[:3])
            return score, f"Shares your focus on {shared}."
        return score, "A different direction from your current goal — could broaden your network."


async def get_cohort_service(
    db: AsyncClient = Depends(get_firestore_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> CohortService:
    return CohortService(FirestoreCohortRepository(db), sessions)
