"""Monthly plan domain — Firestore repository (collection: ``monthly_plans``).

Documents are addressed by a deterministic ``{user_id}_{month_id}`` id so a plan
can be fetched directly by month without a query.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreMonthlyPlanRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "monthly_plans")

    @staticmethod
    def doc_id(user_id: str, month_id: str) -> str:
        return f"{user_id}_{month_id}"
