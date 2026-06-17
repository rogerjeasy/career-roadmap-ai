"""Newsletter domain — service layer.

One preferences document per user, keyed by ``user_id``. ``get`` returns sensible
defaults (unsubscribed) when the user has never set preferences; ``update``
upserts — creating the document on first save, patching it thereafter.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.newsletter.firestore_repository import FirestoreNewsletterRepository
from src.domains.newsletter.schemas import NewsletterPrefsOut, NewsletterPrefsUpdate

logger = get_logger(__name__)


class NewsletterService:
    def __init__(self, repo: FirestoreNewsletterRepository) -> None:
        self._repo = repo

    async def get(self, user_id: str) -> NewsletterPrefsOut:
        doc = await self._repo.get(user_id, user_id)
        if doc is None:
            return NewsletterPrefsOut.defaults()
        return NewsletterPrefsOut.from_doc(doc)

    async def update(
        self, user_id: str, payload: NewsletterPrefsUpdate
    ) -> NewsletterPrefsOut:
        data = payload.model_dump()
        existing = await self._repo.get(user_id, user_id)
        if existing is None:
            doc = await self._repo.create(user_id, data, doc_id=user_id)
        else:
            doc = await self._repo.update(user_id, user_id, data)
        logger.info(
            "newsletter.prefs_updated",
            user_id=user_id,
            subscribed=payload.subscribed,
            frequency=payload.frequency,
        )
        return NewsletterPrefsOut.from_doc(doc or {"id": user_id, **data})


async def get_newsletter_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> NewsletterService:
    return NewsletterService(FirestoreNewsletterRepository(db))
