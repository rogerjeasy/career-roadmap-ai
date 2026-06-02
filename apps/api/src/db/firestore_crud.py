"""Generic user-scoped CRUD over a single Firestore collection.

Shared foundation for the simple user-data domains (books, schedule, networking,
progress, monthly_plan, notifications). Each document always carries the reserved
fields ``user_id``, ``created_at``, ``updated_at`` and ``deleted_at``.

Per-user isolation is enforced on every operation: reads scoped to another user
return ``None`` / are skipped, and writes against another user's document raise
``AuthorizationError``. This mirrors the row-level isolation rule in the project
guide — repositories always filter by the authenticated ``uid``.

Sorting is done in Python (newest-first by ``created_at``) so these domains do
not require Firestore composite indexes, matching the roadmap repository's
approach.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import AuthorizationError
from src.core.logging import get_logger

logger = get_logger(__name__)


def utcnow() -> datetime:
    """Timezone-aware current UTC timestamp (Firestore stores these natively)."""
    return datetime.now(timezone.utc)


class FirestoreCrudRepository:
    """User-scoped create/read/update/delete over one Firestore collection.

    Accepts an ``AsyncClient`` via the constructor — inject the real client in
    production (``get_firestore_client``) or any compatible async mock in tests.
    Documents are plain ``dict`` payloads; (de)serialisation to Pydantic models
    is the responsibility of the owning domain service.
    """

    def __init__(self, db: AsyncClient, collection: str) -> None:
        self._db = db
        self._col = db.collection(collection)
        self._name = collection

    async def create(
        self,
        user_id: str,
        data: dict[str, Any],
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a document owned by ``user_id``; returns the stored doc with ``id``."""
        doc_id = doc_id or str(uuid4())
        now = utcnow()
        payload: dict[str, Any] = {
            **data,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self._col.document(doc_id).set(payload)
        logger.info(f"{self._name}.created", doc_id=doc_id, user_id=user_id)
        return {"id": doc_id, **payload}

    async def get(
        self,
        doc_id: str,
        user_id: str,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        """Return the document if it exists and belongs to ``user_id``, else None."""
        snap = await self._col.document(doc_id).get()
        if not snap.exists:
            return None
        data: dict[str, Any] = snap.to_dict() or {}
        if data.get("user_id") != user_id:
            return None
        if not include_deleted and data.get("deleted_at") is not None:
            return None
        return {"id": snap.id, **data}

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 100,
        include_deleted: bool = False,
        order_desc: bool = True,
    ) -> list[dict[str, Any]]:
        """Return the user's documents, newest-first by ``created_at``."""
        query = self._col.where("user_id", "==", user_id).limit(limit * 2)
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            data: dict[str, Any] = snap.to_dict() or {}
            if not include_deleted and data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        out.sort(key=lambda d: d.get("created_at") or utcnow(), reverse=order_desc)
        return out[:limit]

    async def update(
        self,
        doc_id: str,
        user_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply a partial update after verifying ownership; returns the merged doc.

        Returns ``None`` when the document does not exist. Raises
        ``AuthorizationError`` when the caller is not the owner.
        """
        ref = self._col.document(doc_id)
        snap = await ref.get()
        if not snap.exists:
            return None
        data: dict[str, Any] = snap.to_dict() or {}
        if data.get("user_id") != user_id:
            raise AuthorizationError(f"Document {doc_id!r} is not owned by the caller")
        merged_patch = {**patch, "updated_at": utcnow()}
        await ref.update(merged_patch)
        logger.info(f"{self._name}.updated", doc_id=doc_id, user_id=user_id)
        return {"id": doc_id, **data, **merged_patch}

    async def soft_delete(self, doc_id: str, user_id: str) -> bool:
        """Mark ``deleted_at``; returns False when the doc is missing."""
        ref = self._col.document(doc_id)
        snap = await ref.get()
        if not snap.exists:
            return False
        if (snap.to_dict() or {}).get("user_id") != user_id:
            raise AuthorizationError(f"Document {doc_id!r} is not owned by the caller")
        await ref.update({"deleted_at": utcnow(), "updated_at": utcnow()})
        logger.info(f"{self._name}.soft_deleted", doc_id=doc_id, user_id=user_id)
        return True

    async def hard_delete(self, doc_id: str, user_id: str) -> bool:
        """Permanently remove the document; returns False when it is missing."""
        ref = self._col.document(doc_id)
        snap = await ref.get()
        if not snap.exists:
            return False
        if (snap.to_dict() or {}).get("user_id") != user_id:
            raise AuthorizationError(f"Document {doc_id!r} is not owned by the caller")
        await ref.delete()
        logger.info(f"{self._name}.hard_deleted", doc_id=doc_id, user_id=user_id)
        return True
