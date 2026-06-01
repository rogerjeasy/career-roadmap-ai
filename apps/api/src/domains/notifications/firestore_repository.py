"""Notifications domain — Firestore repository.

Collection: ``notifications`` — flat per-user documents. Bulk read-state
operations filter ``read`` in Python so no composite index is required.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository, utcnow

_COLLECTION = "notifications"


class FirestoreNotificationRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, _COLLECTION)

    async def mark_all_read(self, user_id: str) -> int:
        """Set ``read=True`` on every unread notification; returns the count updated."""
        query = self._col.where("user_id", "==", user_id).limit(500)
        batch = self._db.batch()
        count = 0
        async for snap in query.stream():
            data = snap.to_dict() or {}
            if data.get("read") or data.get("deleted_at") is not None:
                continue
            batch.update(snap.reference, {"read": True, "updated_at": utcnow()})
            count += 1
        if count:
            await batch.commit()
        return count

    async def count_unread(self, user_id: str) -> int:
        query = self._col.where("user_id", "==", user_id).limit(500)
        count = 0
        async for snap in query.stream():
            data = snap.to_dict() or {}
            if not data.get("read") and data.get("deleted_at") is None:
                count += 1
        return count
