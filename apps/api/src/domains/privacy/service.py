"""Privacy domain — service layer.

Exports and purges the user's data across the owner-scoped collections, and
completes account deletion by delegating Firebase/profile removal to the existing
``UserService.delete_account``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository
from src.domains.user.service import UserService, get_user_service

logger = get_logger(__name__)

# Owner-scoped collections that store a ``user_id`` field. Shared/multi-party
# resources (cohorts, mentor_sessions, case_studies) are deliberately omitted.
_USER_COLLECTIONS: tuple[str, ...] = (
    "evidence",
    "portfolio",
    "portfolio_plans",
    "skill_credentials",
    "learning_items",
    "wellness_checkins",
    "oss_bookmarks",
    "story_drafts",
    "applications",
    "roadmap_options",
    "roadmap_snapshots",
    "career_twin_persona",
    "twin_checkins",
    "api_keys",
    "interview_sessions",
    "offer_analyses",
    "mentor_profiles",
    "cohort_checkins",
    "autopilot_proposals",
    "weekly_reviews",
    "habits",
    "books",
    "monthly_plans",
    "notifications",
    "discovery",
    "newsletter",
)


class PrivacyService:
    def __init__(self, db: AsyncClient, users: UserService) -> None:
        self._db = db
        self._users = users

    async def export(self, user_id: str) -> dict[str, Any]:
        collections: dict[str, list[dict[str, Any]]] = {}
        for name in _USER_COLLECTIONS:
            repo = FirestoreCrudRepository(self._db, name)
            docs = await repo.list_for_user(user_id, limit=2000, include_deleted=True)
            if docs:
                collections[name] = docs
        logger.info("privacy.exported", user_id=user_id, collections=len(collections))
        return {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "collections": collections,
        }

    async def purge_data(self, user_id: str) -> int:
        """Hard-delete the user's docs across every owner-scoped collection."""
        removed = 0
        for name in _USER_COLLECTIONS:
            repo = FirestoreCrudRepository(self._db, name)
            docs = await repo.list_for_user(user_id, limit=2000, include_deleted=True)
            for d in docs:
                try:
                    if await repo.hard_delete(d["id"], user_id):
                        removed += 1
                except Exception:  # noqa: BLE001 — best-effort; continue purging
                    logger.warning("privacy.purge_doc_failed", collection=name, doc_id=d.get("id"))
        logger.info("privacy.purged", user_id=user_id, removed=removed)
        return removed

    async def delete_account(self, user_id: str) -> None:
        """Purge all feature data, then delete the Firebase user + profile."""
        await self.purge_data(user_id)
        await self._users.delete_account(user_id)
        logger.info("privacy.account_fully_deleted", user_id=user_id)


async def get_privacy_service(
    db: AsyncClient = Depends(get_firestore_client),
    users: UserService = Depends(get_user_service),
) -> PrivacyService:
    return PrivacyService(db, users)
