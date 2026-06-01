"""Schedule domain — Firestore repositories.

Two flat collections:
  ``habits``          — recurring habits with streak + last_completed_at
  ``schedule_blocks`` — weekly time blocks (one per day cell)
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreHabitRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "habits")


class FirestoreScheduleBlockRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "schedule_blocks")
