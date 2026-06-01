"""Progress domain — Firestore repositories.

Collections:
  ``weekly_reviews`` — append-only weekly reflections (one doc per submission)
  ``career_health``  — one snapshot document per user (doc id == user_id)
"""
from __future__ import annotations

from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository, utcnow


class FirestoreWeeklyReviewRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "weekly_reviews")


class FirestoreHealthRepository:
    """Single-document-per-user career-health snapshot store."""

    def __init__(self, db: AsyncClient) -> None:
        self._col = db.collection("career_health")

    async def get(self, user_id: str) -> dict[str, Any] | None:
        snap = await self._col.document(user_id).get()
        return snap.to_dict() if snap.exists else None

    async def upsert(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {**data, "user_id": user_id, "updated_at": utcnow()}
        await self._col.document(user_id).set(payload, merge=True)
        return payload
