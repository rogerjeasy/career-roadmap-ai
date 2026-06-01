"""Progress domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.progress.firestore_repository import (
    FirestoreHealthRepository,
    FirestoreWeeklyReviewRepository,
)
from src.domains.progress.schemas import (
    HealthSnapshotIn,
    HealthSnapshotOut,
    WeeklyReviewCreate,
    WeeklyReviewOut,
)

logger = get_logger(__name__)


class ProgressService:
    def __init__(
        self,
        reviews: FirestoreWeeklyReviewRepository,
        health: FirestoreHealthRepository,
    ) -> None:
        self._reviews = reviews
        self._health = health

    # ── Weekly reviews ────────────────────────────────────────────────────────

    async def list_reviews(self, user_id: str, limit: int = 26) -> list[WeeklyReviewOut]:
        docs = await self._reviews.list_for_user(user_id, limit=limit)
        return [WeeklyReviewOut.from_doc(d) for d in docs]

    async def create_review(self, user_id: str, payload: WeeklyReviewCreate) -> WeeklyReviewOut:
        doc = await self._reviews.create(user_id, payload.model_dump())
        return WeeklyReviewOut.from_doc(doc)

    # ── Career health ─────────────────────────────────────────────────────────

    async def get_health(self, user_id: str) -> HealthSnapshotOut:
        doc = await self._health.get(user_id)
        return HealthSnapshotOut.from_doc(doc) if doc else HealthSnapshotOut.empty()

    async def set_health(self, user_id: str, payload: HealthSnapshotIn) -> HealthSnapshotOut:
        doc = await self._health.upsert(
            user_id,
            {
                "score": payload.score,
                "delta": payload.delta,
                "signals": [s.model_dump() for s in payload.signals],
            },
        )
        return HealthSnapshotOut.from_doc(doc)


async def get_progress_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> ProgressService:
    return ProgressService(
        FirestoreWeeklyReviewRepository(db),
        FirestoreHealthRepository(db),
    )
