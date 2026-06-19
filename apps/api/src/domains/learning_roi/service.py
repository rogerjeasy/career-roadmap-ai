"""Learning ROI Tracker — service layer.

CRUD over the user's logged learning investments, plus a ranked read that scores
every item against the user's *current* market signals (trending + gap skills and
target role pulled from the cached session snapshot). Scores are computed on read
rather than persisted, so a refreshed market snapshot immediately re-ranks the
list without a migration.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.learning_roi.engine import RoiSignals, score_item
from src.domains.learning_roi.firestore_repository import FirestoreLearningRoiRepository
from src.domains.learning_roi.schemas import (
    LearningItemCreate,
    LearningItemOut,
    LearningItemUpdate,
    LearningRoiSummary,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)


class LearningRoiService:
    def __init__(
        self,
        repo: FirestoreLearningRoiRepository,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._sessions = sessions

    # ── Reads (ranked) ────────────────────────────────────────────────────────

    async def list_ranked(self, user_id: str) -> list[LearningItemOut]:
        docs = await self._repo.list_for_user(user_id, limit=200)
        signals = await self._build_signals(user_id)
        items = [self._score(LearningItemOut.from_doc(d), signals) for d in docs]
        items.sort(key=lambda i: (i.roi_score, i.impact_score), reverse=True)
        for rank, item in enumerate(items, start=1):
            item.rank = rank
        return items

    async def summary(self, user_id: str) -> LearningRoiSummary:
        items = await self.list_ranked(user_id)
        signals = await self._build_signals(user_id)
        if not items:
            return LearningRoiSummary(
                total_items=0,
                total_cost=0.0,
                total_hours=0.0,
                average_roi=0,
                has_market_signals=bool(signals.demand_skills),
            )
        total_cost = round(sum(i.cost for i in items), 2)
        total_hours = round(sum(i.hours for i in items), 1)
        avg_roi = round(sum(i.roi_score for i in items) / len(items))
        return LearningRoiSummary(
            total_items=len(items),
            total_cost=total_cost,
            total_hours=total_hours,
            average_roi=avg_roi,
            top_item_id=items[0].id,
            has_market_signals=bool(signals.demand_skills),
        )

    # ── Writes ────────────────────────────────────────────────────────────────

    async def create(self, user_id: str, payload: LearningItemCreate) -> LearningItemOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        signals = await self._build_signals(user_id)
        logger.info("learning_roi.created", user_id=user_id, item_id=doc["id"])
        return self._score(LearningItemOut.from_doc(doc), signals)

    async def update(
        self, user_id: str, item_id: str, payload: LearningItemUpdate
    ) -> LearningItemOut:
        patch = payload.to_patch()
        doc = await self._repo.update(item_id, user_id, patch) if patch else \
            await self._repo.get(item_id, user_id)
        if doc is None:
            raise NotFoundError("Learning item not found.")
        signals = await self._build_signals(user_id)
        return self._score(LearningItemOut.from_doc(doc), signals)

    async def delete(self, user_id: str, item_id: str) -> None:
        removed = await self._repo.soft_delete(item_id, user_id)
        if not removed:
            raise NotFoundError("Learning item not found.")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _score(self, item: LearningItemOut, signals: RoiSignals) -> LearningItemOut:
        scored = score_item(
            skills=item.skills,
            cost=item.cost,
            hours=item.hours,
            item_type=item.type,
            signals=signals,
        )
        item.impact_score = scored.impact_score
        item.relevance = scored.relevance
        item.roi_score = scored.roi_score
        item.matched_skills = scored.matched_skills
        item.rationale = scored.rationale
        return item

    async def _build_signals(self, user_id: str) -> RoiSignals:
        session = await self._sessions.get(user_id)
        if session is None:
            return RoiSignals()
        profile = session.user_profile_context
        target_role = profile.target_role if profile else None
        demand = self._demand_skills(session, profile)
        return RoiSignals(demand_skills=demand, target_role=target_role)

    @staticmethod
    def _demand_skills(session: Any, profile: Any) -> list[str]:
        """Trending market skills + declared skill gaps, deduped and lowercased."""
        if session.plan_context is None:
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
        out: list[str] = []
        for item in market.get("trending_skills") or []:
            if isinstance(item, dict) and item.get("name"):
                out.append(str(item["name"]))
            elif isinstance(item, str):
                out.append(item)
        # Skill gaps from CV analysis, if present.
        cv = (
            snapshot.get("cv")
            or snapshot.get("cv_analysis")
            or agent_outputs.get("cv")
            or agent_outputs.get("cv_analysis")
            or {}
        )
        for gap in cv.get("skill_gaps") or cv.get("missing_skills") or []:
            if isinstance(gap, dict) and gap.get("skill"):
                out.append(str(gap["skill"]))
            elif isinstance(gap, str):
                out.append(gap)
        seen: set[str] = set()
        deduped: list[str] = []
        for s in out:
            key = s.strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(s.strip())
        return deduped


async def get_learning_roi_service(
    db: AsyncClient = Depends(get_firestore_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> LearningRoiService:
    return LearningRoiService(FirestoreLearningRoiRepository(db), sessions)
