"""Accountability Cohorts — Firestore repository.

Two collections:
  ``cohorts``          — the shared group documents (membership-based access)
  ``cohort_checkins``  — per-member check-ins, queried by cohort

Membership access means the generic owner-scoped CRUD base does not apply: a
member who did not create the cohort must still be able to read it and its
check-ins. Single-field ``where`` filters are used and any ordering is done in
Python, matching the project's no-composite-index convention.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from src.core.logging import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FirestoreCohortRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._cohorts = db.collection("cohorts")
        self._checkins = db.collection("cohort_checkins")

    # ── Cohorts ───────────────────────────────────────────────────────────────

    async def create(self, owner_id: str, owner_name: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(uuid4())
        now = _utcnow()
        member = {"uid": owner_id, "name": owner_name, "joined_at": now}
        payload: dict[str, Any] = {
            **data,
            "created_by": owner_id,
            "status": "open",
            "members": [member],
            "member_ids": [owner_id],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self._cohorts.document(doc_id).set(payload)
        logger.info("cohort.created", cohort_id=doc_id, owner_id=owner_id)
        return {"id": doc_id, **payload}

    async def get(self, cohort_id: str) -> dict[str, Any] | None:
        snap = await self._cohorts.document(cohort_id).get()
        if not snap.exists:
            return None
        data: dict[str, Any] = snap.to_dict() or {}
        if data.get("deleted_at") is not None:
            return None
        return {"id": snap.id, **data}

    async def list_for_member(self, user_id: str) -> list[dict[str, Any]]:
        query = self._cohorts.where(
            filter=FieldFilter("member_ids", "array_contains", user_id)
        )
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            data: dict[str, Any] = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        out.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return out

    async def list_open(self, limit: int = 100) -> list[dict[str, Any]]:
        query = self._cohorts.where(filter=FieldFilter("status", "==", "open")).limit(limit * 2)
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            data: dict[str, Any] = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        out.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return out[:limit]

    async def update(self, cohort_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        ref = self._cohorts.document(cohort_id)
        snap = await ref.get()
        if not snap.exists:
            return None
        data: dict[str, Any] = snap.to_dict() or {}
        merged = {**patch, "updated_at": _utcnow()}
        await ref.update(merged)
        return {"id": cohort_id, **data, **merged}

    async def soft_delete(self, cohort_id: str) -> None:
        await self._cohorts.document(cohort_id).update(
            {"deleted_at": _utcnow(), "updated_at": _utcnow(), "status": "archived"}
        )

    # ── Check-ins ─────────────────────────────────────────────────────────────

    async def add_checkin(self, cohort_id: str, user_id: str, user_name: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(uuid4())
        now = _utcnow()
        payload = {
            **data,
            "cohort_id": cohort_id,
            "user_id": user_id,
            "user_name": user_name,
            "created_at": now,
        }
        await self._checkins.document(doc_id).set(payload)
        return {"id": doc_id, **payload}

    async def list_checkins(self, cohort_id: str, limit: int = 50) -> list[dict[str, Any]]:
        query = self._checkins.where(
            filter=FieldFilter("cohort_id", "==", cohort_id)
        ).limit(limit * 2)
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            out.append({"id": snap.id, **(snap.to_dict() or {})})
        out.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return out[:limit]
