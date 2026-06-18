"""Newsletter domain — Firestore repository (collection: ``newsletter_prefs``)."""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreNewsletterRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "newsletter_prefs")


class FirestoreNewsletterDigestRepository(FirestoreCrudRepository):
    """Latest generated digest per user (collection ``newsletter_digests``, doc id == uid)."""

    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "newsletter_digests")
