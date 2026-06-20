"""Exports — service layer.

Loads an owner-scoped roadmap and renders it to Markdown or iCalendar via the
pure generators.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.db.firestore import get_firestore_client
from src.domains.exports.generators import roadmap_to_ics, roadmap_to_markdown
from src.domains.roadmap.firestore_repository import FirestoreRoadmapRepository


class ExportService:
    def __init__(self, roadmaps: FirestoreRoadmapRepository) -> None:
        self._roadmaps = roadmaps

    async def roadmap_markdown(self, user_id: str, roadmap_id: str) -> str:
        doc = await self._roadmaps.get(roadmap_id, user_id)
        if doc is None:
            raise NotFoundError("Roadmap not found.")
        return roadmap_to_markdown(doc)

    async def roadmap_ics(self, user_id: str, roadmap_id: str) -> str:
        doc = await self._roadmaps.get(roadmap_id, user_id)
        if doc is None:
            raise NotFoundError("Roadmap not found.")
        return roadmap_to_ics(doc)


async def get_export_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> ExportService:
    return ExportService(FirestoreRoadmapRepository(db))
