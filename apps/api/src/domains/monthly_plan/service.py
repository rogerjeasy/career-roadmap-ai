"""Monthly plan domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.monthly_plan.firestore_repository import FirestoreMonthlyPlanRepository
from src.domains.monthly_plan.schemas import (
    MonthlyPlanOut,
    MonthlyPlanSummaryOut,
    MonthlyPlanUpsert,
)

logger = get_logger(__name__)


class MonthlyPlanService:
    def __init__(self, repo: FirestoreMonthlyPlanRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str) -> list[MonthlyPlanSummaryOut]:
        docs = await self._repo.list_for_user(user_id, limit=60, order_desc=False)
        docs.sort(key=lambda d: d.get("month_id", ""))
        return [MonthlyPlanSummaryOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, month_id: str) -> MonthlyPlanOut:
        doc = await self._repo.get(self._repo.doc_id(user_id, month_id), user_id)
        if doc is None:
            raise NotFoundError(f"Monthly plan '{month_id}' not found")
        return MonthlyPlanOut.from_doc(doc)

    async def upsert(self, user_id: str, payload: MonthlyPlanUpsert) -> MonthlyPlanOut:
        doc_id = self._repo.doc_id(user_id, payload.month_id)
        data = payload.model_dump()
        existing = await self._repo.get(doc_id, user_id)
        if existing is None:
            doc = await self._repo.create(user_id, data, doc_id=doc_id)
        else:
            doc = await self._repo.update(doc_id, user_id, data)
            assert doc is not None  # existence verified above
        return MonthlyPlanOut.from_doc(doc)

    async def delete(self, user_id: str, month_id: str) -> None:
        deleted = await self._repo.hard_delete(self._repo.doc_id(user_id, month_id), user_id)
        if not deleted:
            raise NotFoundError(f"Monthly plan '{month_id}' not found")


async def get_monthly_plan_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> MonthlyPlanService:
    return MonthlyPlanService(FirestoreMonthlyPlanRepository(db))
