"""Public API Keys — Firestore repository (collection: ``api_keys``).

Adds a collection-wide ``get_by_hash`` lookup used by the API-key authenticator,
which has no authenticated user and must resolve a presented key to its owner.
"""
from __future__ import annotations

from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreApiKeyRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "api_keys")

    async def get_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        if not key_hash:
            return None
        query = self._col.where("key_hash", "==", key_hash).limit(1)
        async for snap in query.stream():
            data: dict[str, Any] = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            return {"id": snap.id, **data}
        return None
