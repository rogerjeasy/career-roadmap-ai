"""Public API Keys — service layer.

Mints and manages personal API keys (hashed at rest) and authenticates a
presented key back to its owner. The public read endpoint uses ``authenticate``
to resolve the caller, then reads that user's cached profile + roadmap summary.
"""
from __future__ import annotations

import hashlib
import secrets as secretslib

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.api_keys.firestore_repository import FirestoreApiKeyRepository
from src.domains.api_keys.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    PublicPhase,
    PublicProfile,
    PublicRoadmap,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_KEY_PREFIX = "cra_live_"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ApiKeyService:
    def __init__(self, repo: FirestoreApiKeyRepository, sessions: SessionManager) -> None:
        self._repo = repo
        self._sessions = sessions

    # ── Key management (Firebase-authenticated) ───────────────────────────────

    async def list(self, user_id: str) -> list[ApiKeyOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [ApiKeyOut.from_doc(d) for d in docs]

    async def create(self, user_id: str, payload: ApiKeyCreate) -> ApiKeyCreated:
        secret = secretslib.token_urlsafe(24)
        raw = f"{_KEY_PREFIX}{secret}"
        doc = await self._repo.create(
            user_id,
            {
                "name": payload.name.strip(),
                "key_hash": _hash_key(raw),
                "prefix": raw[: len(_KEY_PREFIX) + 4],
                "last4": raw[-4:],
                "revoked": False,
                "last_used_at": None,
            },
        )
        logger.info("api_key.created", user_id=user_id, key_id=doc["id"])
        out = ApiKeyOut.from_doc(doc)
        return ApiKeyCreated(**out.model_dump(), key=raw)

    async def revoke(self, user_id: str, key_id: str) -> ApiKeyOut:
        doc = await self._repo.update(key_id, user_id, {"revoked": True})
        if doc is None:
            raise NotFoundError("API key not found.")
        logger.info("api_key.revoked", user_id=user_id, key_id=key_id)
        return ApiKeyOut.from_doc(doc)

    async def delete(self, user_id: str, key_id: str) -> None:
        removed = await self._repo.hard_delete(key_id, user_id)
        if not removed:
            raise NotFoundError("API key not found.")

    # ── Key authentication (public API) ───────────────────────────────────────

    async def authenticate(self, presented_key: str) -> str | None:
        """Return the owning user_id for a valid, non-revoked key, else None."""
        doc = await self._repo.get_by_hash(_hash_key(presented_key))
        if doc is None or doc.get("revoked"):
            return None
        user_id = doc.get("user_id")
        # Best-effort last-used stamp; never block auth on the write.
        try:
            await self._repo.update(doc["id"], user_id, {"last_used_at": utcnow()})
        except Exception:  # noqa: BLE001
            pass
        return user_id

    async def public_roadmap(self, user_id: str) -> PublicRoadmap:
        session = await self._sessions.get(user_id)
        plan = session.plan_context if session else None
        if plan is None or not isinstance(plan.snapshot, dict):
            return PublicRoadmap(has_roadmap=bool(plan and plan.roadmap_id))
        snapshot = plan.snapshot
        raw_phases = snapshot.get("phases") or []
        phases = [
            PublicPhase(
                order=int(p.get("order", i + 1) or i + 1),
                title=str(p.get("title", "")),
                duration_weeks=int(p.get("duration_weeks", 0) or 0),
                milestones=list(p.get("milestones", []) or [])[:10],
            )
            for i, p in enumerate(raw_phases)
            if isinstance(p, dict)
        ]
        summary = snapshot.get("summary")
        return PublicRoadmap(
            has_roadmap=bool(plan.roadmap_id),
            summary=summary if isinstance(summary, str) else None,
            phase_count=len(phases),
            phases=phases,
        )

    async def public_profile(self, user_id: str) -> PublicProfile:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        plan = session.plan_context if session else None
        summary = None
        if plan is not None and isinstance(plan.snapshot, dict):
            s = plan.snapshot.get("summary")
            summary = s if isinstance(s, str) else None
        return PublicProfile(
            user_id=user_id,
            target_role=profile.target_role if profile else None,
            current_role=profile.current_role if profile else None,
            location=profile.location if profile else None,
            skills=list(profile.skills) if profile and profile.skills else [],
            has_roadmap=bool(plan and plan.roadmap_id),
            roadmap_summary=summary,
        )


async def get_api_key_service(
    db: AsyncClient = Depends(get_firestore_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> ApiKeyService:
    return ApiKeyService(FirestoreApiKeyRepository(db), sessions)
