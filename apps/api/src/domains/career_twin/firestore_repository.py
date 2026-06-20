"""Career Twin — Firestore repositories.

``career_twin_persona`` holds one persona doc per user (id == user_id).
``twin_checkins`` holds the dated check-in journal entries.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreTwinPersonaRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "career_twin_persona")


class FirestoreTwinCheckinRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "twin_checkins")
