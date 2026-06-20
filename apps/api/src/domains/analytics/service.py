"""Analytics domain — service layer.

Reads owner-scoped collections directly via the generic CRUD repository and folds
them into a single overview. Each section degrades to zeros when a feature hasn't
been used yet, so the dashboard is always renderable.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.analytics.schemas import (
    AnalyticsOverview,
    ApplicationsFunnel,
    AssetCounts,
    LearningSummary,
    MomentumSummary,
    WellnessSummary,
)

_TERMINAL = {"rejected", "accepted", "withdrawn"}


class AnalyticsService:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    def _col(self, name: str) -> FirestoreCrudRepository:
        return FirestoreCrudRepository(self._db, name)

    async def overview(self, user_id: str) -> AnalyticsOverview:
        return AnalyticsOverview(
            applications=await self._applications(user_id),
            learning=await self._learning(user_id),
            wellness=await self._wellness(user_id),
            assets=await self._assets(user_id),
            momentum=await self._momentum(user_id),
        )

    async def _applications(self, user_id: str) -> ApplicationsFunnel:
        docs = await self._col("applications").list_for_user(user_id, limit=500)
        by_status: dict[str, int] = {}
        for d in docs:
            s = str(d.get("status", "saved"))
            by_status[s] = by_status.get(s, 0) + 1
        applied_plus = sum(
            c for s, c in by_status.items() if s != "saved"
        )
        interviewing_plus = sum(
            by_status.get(s, 0) for s in ("interviewing", "offer", "accepted")
        )
        offers = by_status.get("offer", 0) + by_status.get("accepted", 0)
        active = sum(c for s, c in by_status.items() if s not in _TERMINAL)
        return ApplicationsFunnel(
            total=len(docs),
            by_status=by_status,
            active=active,
            offers=offers,
            interview_rate=round(interviewing_plus / applied_plus, 2) if applied_plus else 0.0,
            offer_rate=round(offers / applied_plus, 2) if applied_plus else 0.0,
        )

    async def _learning(self, user_id: str) -> LearningSummary:
        docs = await self._col("learning_items").list_for_user(user_id, limit=500)
        if not docs:
            return LearningSummary()
        cost = sum(float(d.get("cost", 0) or 0) for d in docs)
        hours = sum(float(d.get("hours", 0) or 0) for d in docs)
        return LearningSummary(
            items=len(docs),
            total_cost=round(cost, 2),
            total_hours=round(hours, 1),
            avg_roi=0,  # ROI is computed on read in its own service; left 0 here
        )

    async def _wellness(self, user_id: str) -> WellnessSummary:
        docs = await self._col("wellness_checkins").list_for_user(user_id, limit=20)
        if not docs:
            return WellnessSummary()
        latest = docs[0]
        # Lightweight inline risk read avoids importing the wellness engine.
        energy = int(latest.get("energy", 3) or 3)
        stress = int(latest.get("stress", 3) or 3)
        idx = stress - energy  # higher → worse
        level = "high" if idx >= 2 else "moderate" if idx >= 0 else "low"
        return WellnessSummary(checkins=len(docs), latest_risk=None, latest_level=level)

    async def _assets(self, user_id: str) -> AssetCounts:
        async def count(name: str) -> int:
            return len(await self._col(name).list_for_user(user_id, limit=500))

        return AssetCounts(
            evidence=await count("evidence"),
            portfolio=await count("portfolio"),
            credentials=await count("skill_credentials"),
            story_drafts=await count("story_drafts"),
            oss_bookmarks=await count("oss_bookmarks"),
        )

    async def _momentum(self, user_id: str) -> MomentumSummary:
        reviews = await self._col("weekly_reviews").list_for_user(user_id, limit=200)
        habits = await self._col("habits").list_for_user(user_id, limit=200)
        interviews = await self._col("interview_sessions").list_for_user(user_id, limit=200)
        days: int | None = None
        if reviews:
            created = reviews[0].get("created_at")
            if created is not None:
                try:
                    days = max(0, (utcnow() - created).days)
                except TypeError:
                    days = None
        return MomentumSummary(
            weekly_reviews=len(reviews),
            days_since_review=days,
            habits_tracked=len(habits),
            interview_practices=len(interviews),
        )


async def get_analytics_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> AnalyticsService:
    return AnalyticsService(db)
