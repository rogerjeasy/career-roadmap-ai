"""Schedule domain — Firestore repositories.

Flat collections:
  ``habits``                  — recurring habits with streak + last_completed_at
  ``schedule_blocks``         — weekly time blocks (one per day cell)
  ``schedule_time_logs``      — logged hours entries (category + hours + date)
  ``schedule_budget_targets`` — per-user weekly target hours (doc_id == user_id)
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


class FirestoreTimeLogRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "schedule_time_logs")


class FirestoreBudgetTargetRepository(FirestoreCrudRepository):
    """One document per user (``doc_id == user_id``) holding weekly target hours."""

    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "schedule_budget_targets")
