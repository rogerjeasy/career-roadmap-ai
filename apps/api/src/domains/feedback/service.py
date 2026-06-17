"""Feedback domain — service layer.

Users can submit feedback / help requests and see their own submission history.
Submissions are immutable once filed (no update/delete) — they form an audit
trail the team can triage. Listing is always scoped to the authenticated user.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.feedback.firestore_repository import FirestoreFeedbackRepository
from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut

logger = get_logger(__name__)


class FeedbackService:
    def __init__(self, repo: FirestoreFeedbackRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str, limit: int = 50) -> list[FeedbackOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [FeedbackOut.from_doc(d) for d in docs]

    async def create(self, user_id: str, payload: FeedbackCreate) -> FeedbackOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        logger.info(
            "feedback.submitted",
            user_id=user_id,
            feedback_id=doc["id"],
            category=payload.category,
        )
        return FeedbackOut.from_doc(doc)


async def get_feedback_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> FeedbackService:
    return FeedbackService(FirestoreFeedbackRepository(db))
