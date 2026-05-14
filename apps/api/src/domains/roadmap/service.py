"""Roadmap domain — service layer.

``RoadmapService`` accepts an ``IRoadmapRepository`` via the constructor.
Swap the repository in tests without touching any FastAPI internals:

    repo = MagicMock()
    repo.get = AsyncMock(return_value=some_doc)
    service = RoadmapService(repo)
"""
from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.roadmap.interfaces import IRoadmapRepository
from src.domains.roadmap.schemas import RoadmapDocument, RoadmapSummary

logger = get_logger(__name__)


class RoadmapService:
    def __init__(self, repo: IRoadmapRepository) -> None:
        self._repo = repo

    async def get(self, roadmap_id: str, user_id: str) -> RoadmapDocument | None:
        return await self._repo.get(roadmap_id, user_id)

    async def list_for_user(self, user_id: str, limit: int = 20) -> list[RoadmapSummary]:
        return await self._repo.list_for_user(user_id, limit=limit)

    async def list_for_user_paginated(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[RoadmapSummary], str | None]:
        from src.domains.roadmap.firestore_repository import FirestoreRoadmapRepository  # noqa: PLC0415

        if not isinstance(self._repo, FirestoreRoadmapRepository):
            summaries = await self._repo.list_for_user(user_id, limit=limit + 1)
            has_more = len(summaries) > limit
            next_cursor = summaries[limit - 1].created_at.isoformat() if has_more else None
            return summaries[:limit], next_cursor

        return await self._repo.list_for_user_paginated(user_id, limit=limit, cursor=cursor)

    async def delete(self, roadmap_id: str, user_id: str) -> None:
        doc = await self._repo.get(roadmap_id, user_id)
        if doc is None:
            raise NotFoundError(f"Roadmap '{roadmap_id}' not found")
        await self._repo.soft_delete(roadmap_id, user_id)
        logger.info("roadmap.service.deleted", roadmap_id=roadmap_id, user_id=user_id)


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_roadmap_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> RoadmapService:
    """Injectable factory — wires FirestoreRoadmapRepository into RoadmapService."""
    from src.domains.roadmap.firestore_repository import FirestoreRoadmapRepository  # noqa: PLC0415

    return RoadmapService(FirestoreRoadmapRepository(db))
