"""Job Applications domain — Firestore repository (collection: ``applications``)."""
from __future__ import annotations

from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreApplicationRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "applications")

    async def iter_all(self, limit: int = 2000) -> list[dict[str, Any]]:
        """Stream every non-deleted application across all users.

        Used by the scheduled reminder sweep, which is a system-level scan rather
        than a per-user read — so it intentionally does not filter by ``user_id``.
        Bounded by ``limit`` to keep a single tick predictable.
        """
        out: list[dict[str, Any]] = []
        async for snap in self._col.limit(limit).stream():
            data: dict[str, Any] = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        return out
