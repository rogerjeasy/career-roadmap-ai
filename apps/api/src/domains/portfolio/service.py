"""Portfolio domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.portfolio.firestore_repository import FirestorePortfolioRepository
from src.domains.portfolio.schemas import (
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
)

logger = get_logger(__name__)


class PortfolioService:
    def __init__(self, repo: FirestorePortfolioRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str, limit: int = 100) -> list[PortfolioItemOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [PortfolioItemOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, item_id: str) -> PortfolioItemOut:
        doc = await self._repo.get(item_id, user_id)
        if doc is None:
            raise NotFoundError(f"Portfolio item '{item_id}' not found")
        return PortfolioItemOut.from_doc(doc)

    async def create(
        self, user_id: str, payload: PortfolioItemCreate
    ) -> PortfolioItemOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        return PortfolioItemOut.from_doc(doc)

    async def update(
        self, user_id: str, item_id: str, payload: PortfolioItemUpdate
    ) -> PortfolioItemOut:
        doc = await self._repo.update(item_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Portfolio item '{item_id}' not found")
        return PortfolioItemOut.from_doc(doc)

    async def delete(self, user_id: str, item_id: str) -> None:
        deleted = await self._repo.hard_delete(item_id, user_id)
        if not deleted:
            raise NotFoundError(f"Portfolio item '{item_id}' not found")


async def get_portfolio_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> PortfolioService:
    return PortfolioService(FirestorePortfolioRepository(db))
