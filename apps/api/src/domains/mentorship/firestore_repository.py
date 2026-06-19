"""Mentorship — Firestore repository (collections: ``mentor_profiles``,
``mentor_sessions``, ``case_studies``).

Mentor profiles are keyed by ``user_id`` (one per user). Sessions are shared
between a mentor and a mentee, so they are queried by either side. Case studies
are world-readable to members. Single-field ``where`` filters only; ordering in
Python (no composite indexes), per project convention.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.cloud.firestore_v1.async_client import AsyncClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FirestoreMentorshipRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._profiles = db.collection("mentor_profiles")
        self._sessions = db.collection("mentor_sessions")
        self._cases = db.collection("case_studies")

    # ── Mentor profiles (doc id == user_id) ───────────────────────────────────

    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        snap = await self._profiles.document(user_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        if data.get("deleted_at") is not None:
            return None
        return {"id": snap.id, **data}

    async def upsert_profile(self, user_id: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self._profiles.document(user_id).get()
        now = _utcnow()
        payload = {
            **data,
            "user_id": user_id,
            "name": name,
            "updated_at": now,
            "deleted_at": None,
        }
        if not existing.exists:
            payload["created_at"] = now
        await self._profiles.document(user_id).set(payload, merge=True)
        merged = {**(existing.to_dict() or {}), **payload}
        return {"id": user_id, **merged}

    async def deactivate_profile(self, user_id: str) -> None:
        await self._profiles.document(user_id).set(
            {"is_active": False, "updated_at": _utcnow()}, merge=True
        )

    async def list_active_profiles(self, limit: int = 100) -> list[dict[str, Any]]:
        query = self._profiles.where("is_active", "==", True).limit(limit * 2)
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            data = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        out.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return out[:limit]

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(uuid4())
        payload = {**data, "status": "requested", "reply": "", "created_at": _utcnow(), "responded_at": None}
        await self._sessions.document(doc_id).set(payload)
        return {"id": doc_id, **payload}

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        snap = await self._sessions.document(session_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **(snap.to_dict() or {})}

    async def update_session(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        ref = self._sessions.document(session_id)
        snap = await ref.get()
        if not snap.exists:
            return None
        await ref.update(patch)
        return {"id": session_id, **(snap.to_dict() or {}), **patch}

    async def list_sessions_for(self, user_id: str, field: str, limit: int = 100) -> list[dict[str, Any]]:
        query = self._sessions.where(field, "==", user_id).limit(limit * 2)
        out: list[dict[str, Any]] = []
        async for snap in query.stream():
            out.append({"id": snap.id, **(snap.to_dict() or {})})
        return out

    # ── Case studies ──────────────────────────────────────────────────────────

    async def create_case(self, author_id: str, author_name: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(uuid4())
        payload = {
            **data,
            "author_id": author_id,
            "author_name": author_name,
            "created_at": _utcnow(),
            "deleted_at": None,
        }
        await self._cases.document(doc_id).set(payload)
        return {"id": doc_id, **payload}

    async def list_cases(self, limit: int = 100) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for snap in self._cases.limit(limit * 2).stream():
            data = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            out.append({"id": snap.id, **data})
        out.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return out[:limit]

    async def get_case(self, case_id: str) -> dict[str, Any] | None:
        snap = await self._cases.document(case_id).get()
        if not snap.exists:
            return None
        return {"id": snap.id, **(snap.to_dict() or {})}

    async def soft_delete_case(self, case_id: str) -> None:
        await self._cases.document(case_id).update({"deleted_at": _utcnow()})
