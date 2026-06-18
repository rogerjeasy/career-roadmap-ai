"""Autopilot domain — service layer.

Assembles real user signals (roadmap presence, weekly-review staleness, habit
consistency, market drift), runs the pure proposal engine, persists any new
proposals (deduped by signature against still-open ones), and exposes
accept/dismiss. Reads come from the session and from the weekly_reviews / habits
collections via the generic CRUD repository.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.autopilot.engine import AutopilotSignals, build_proposals
from src.domains.autopilot.firestore_repository import FirestoreAutopilotRepository
from src.domains.autopilot.schemas import AutopilotProposalOut
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_OPEN = "open"
_HABIT_WEEK_MIN = 2  # fewer than this many completions this week → "slipping"


class AutopilotService:
    def __init__(
        self,
        repo: FirestoreAutopilotRepository,
        reviews: FirestoreCrudRepository,
        habits: FirestoreCrudRepository,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._reviews = reviews
        self._habits = habits
        self._sessions = sessions

    # ── Public API ────────────────────────────────────────────────────────────

    async def list_open(self, user_id: str) -> list[AutopilotProposalOut]:
        docs = await self._repo.list_for_user(user_id, limit=50)
        return [
            AutopilotProposalOut.from_doc(d)
            for d in docs
            if d.get("status", _OPEN) == _OPEN
        ]

    async def refresh(self, user_id: str) -> list[AutopilotProposalOut]:
        """Recompute signals and persist any newly-detected proposals."""
        signals = await self._assemble_signals(user_id)
        candidates = build_proposals(signals)

        existing = await self._repo.list_for_user(user_id, limit=100)
        open_signatures = {
            d.get("signature")
            for d in existing
            if d.get("status", _OPEN) == _OPEN
        }

        for cand in candidates:
            if cand.signature in open_signatures:
                continue
            await self._repo.create(
                user_id,
                {
                    "kind": cand.kind,
                    "title": cand.title,
                    "detail": cand.detail,
                    "severity": cand.severity,
                    "action_label": cand.action_label,
                    "action_route": cand.action_route,
                    "signature": cand.signature,
                    "status": _OPEN,
                },
            )
        logger.info(
            "autopilot.refreshed",
            user_id=user_id,
            candidates=len(candidates),
        )
        return await self.list_open(user_id)

    async def set_status(
        self, user_id: str, proposal_id: str, status: str
    ) -> AutopilotProposalOut | None:
        doc = await self._repo.update(
            proposal_id, user_id, {"status": status, "resolved_at": utcnow()}
        )
        if doc is None:
            return None
        return AutopilotProposalOut.from_doc(doc)

    # ── Signal assembly ───────────────────────────────────────────────────────

    async def _assemble_signals(self, user_id: str) -> AutopilotSignals:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        plan = session.plan_context if session else None

        has_roadmap = bool(plan and plan.roadmap_id)

        days_since_review = await self._days_since_review(user_id)
        low_habits = await self._low_habits(user_id)
        missing = self._missing_trending_skills(session, profile)

        return AutopilotSignals(
            has_roadmap=has_roadmap,
            days_since_review=days_since_review,
            low_habits=low_habits,
            missing_trending_skills=missing,
        )

    async def _days_since_review(self, user_id: str) -> int | None:
        docs = await self._reviews.list_for_user(user_id, limit=1)
        if not docs:
            return None
        created = docs[0].get("created_at")
        if created is None:
            return None
        try:
            return max(0, (utcnow() - created).days)
        except TypeError:
            return None

    async def _low_habits(self, user_id: str) -> list[str]:
        docs = await self._habits.list_for_user(user_id, limit=50)
        low: list[str] = []
        for d in docs:
            week = d.get("week_completions")
            if not isinstance(week, list) or not week:
                continue
            done = sum(1 for x in week if x)
            if done < _HABIT_WEEK_MIN:
                low.append(str(d.get("name") or d.get("title") or d.get("text") or "a habit"))
        return low

    @staticmethod
    def _missing_trending_skills(session: Any, profile: Any) -> list[str]:
        if session is None or session.plan_context is None:
            return []
        snapshot = session.plan_context.snapshot or {}
        if not isinstance(snapshot, dict):
            return []
        agent_outputs = snapshot.get("agent_outputs", {})
        market = (
            snapshot.get("market")
            or snapshot.get("market_intelligence")
            or agent_outputs.get("market")
            or agent_outputs.get("market_intelligence")
            or {}
        )
        trending = market.get("trending_skills") or []
        held = {s.lower() for s in (profile.skills if profile else [])}
        missing: list[str] = []
        for item in trending:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name and name.lower() not in held:
                missing.append(name)
        return missing[:5]


async def get_autopilot_service(
    db: AsyncClient = Depends(get_firestore_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> AutopilotService:
    return AutopilotService(
        FirestoreAutopilotRepository(db),
        FirestoreCrudRepository(db, "weekly_reviews"),
        FirestoreCrudRepository(db, "habits"),
        sessions,
    )
