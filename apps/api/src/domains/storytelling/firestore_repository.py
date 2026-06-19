"""Storytelling domain — Firestore repository (collection: ``story_drafts``)."""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreStorytellingRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "story_drafts")
