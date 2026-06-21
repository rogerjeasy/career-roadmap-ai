"""Verifiable Skill Credentials — Firestore repository (collection: ``skill_credentials``).

Extends the generic user-scoped CRUD base with one collection-wide lookup:
``get_by_token`` powers the *public* verifier, which has no authenticated user
and must locate a credential purely by its share token.
"""
from __future__ import annotations

from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreCredentialRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "skill_credentials")

    async def get_by_token(self, share_token: str) -> dict[str, Any] | None:
        """Collection-wide lookup by share token for unauthenticated verification."""
        if not share_token:
            return None
        query = self._col.where(filter=FieldFilter("share_token", "==", share_token)).limit(1)
        async for snap in query.stream():
            data: dict[str, Any] = snap.to_dict() or {}
            return {"id": snap.id, **data}
        return None
