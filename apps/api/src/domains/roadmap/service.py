"""Roadmap domain — service layer.

``RoadmapService`` accepts an ``IRoadmapRepository`` via the constructor.
Swap the repository in tests without touching any FastAPI internals:

    repo = MagicMock()
    repo.get = AsyncMock(return_value=some_doc)
    service = RoadmapService(repo)
"""
from datetime import datetime

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

    # ── Milestone progress ────────────────────────────────────────────────────

    async def get_progress(
        self, roadmap_id: str, user_id: str
    ) -> tuple[list[str], datetime | None]:
        """Return (completed milestone keys, last-updated) for the user's roadmap."""
        return await self._repo.get_progress(roadmap_id, user_id)

    async def toggle_milestone(
        self, roadmap_id: str, user_id: str, key: str
    ) -> tuple[list[str], datetime]:
        """Flip one milestone's completion state and persist; return the new set."""
        completed, _ = await self._repo.get_progress(roadmap_id, user_id)
        keys = set(completed)
        if key in keys:
            keys.discard(key)
        else:
            keys.add(key)
        ordered = sorted(keys)
        updated = await self._repo.set_progress(roadmap_id, user_id, ordered)
        return ordered, updated

    # ── Phase editing ─────────────────────────────────────────────────────────

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
        """Trim whitespace and drop empty entries from a string list."""
        return [v.strip() for v in values if v and v.strip()]

    async def update_phase(
        self, roadmap_id: str, user_id: str, phase_id: str, updates: dict
    ) -> RoadmapDocument:
        """Apply a partial phase update, reconciling progress when milestones change."""
        if "milestones" in updates:
            updates["milestones"] = self._clean_list(updates["milestones"])
        if "skills_to_gain" in updates:
            updates["skills_to_gain"] = self._clean_list(updates["skills_to_gain"])

        ok = await self._repo.update_phase(roadmap_id, user_id, phase_id, updates)
        if not ok:
            raise NotFoundError(f"Phase '{phase_id}' not found on roadmap '{roadmap_id}'")

        # Editing the milestone list can shrink it — drop any completed keys that
        # now point past the end so progress never references a missing milestone.
        if "milestones" in updates:
            await self._prune_phase_progress(
                roadmap_id, user_id, phase_id, len(updates["milestones"])
            )

        return await self._require(roadmap_id, user_id)

    async def add_phase(
        self, roadmap_id: str, user_id: str, phase_data: dict
    ) -> RoadmapDocument:
        """Append a user-authored phase to the roadmap."""
        phase_data["milestones"] = self._clean_list(phase_data.get("milestones", []))
        phase_data["skills_to_gain"] = self._clean_list(phase_data.get("skills_to_gain", []))
        phase_id = await self._repo.add_phase(roadmap_id, user_id, phase_data)
        if phase_id is None:
            raise NotFoundError(f"Roadmap '{roadmap_id}' not found")
        return await self._require(roadmap_id, user_id)

    async def delete_phase(
        self, roadmap_id: str, user_id: str, phase_id: str
    ) -> RoadmapDocument:
        """Delete a phase and discard its completed-milestone progress."""
        ok = await self._repo.delete_phase(roadmap_id, user_id, phase_id)
        if not ok:
            raise NotFoundError(f"Phase '{phase_id}' not found on roadmap '{roadmap_id}'")
        await self._prune_phase_progress(roadmap_id, user_id, phase_id, 0)
        return await self._require(roadmap_id, user_id)

    async def reorder_phases(
        self, roadmap_id: str, user_id: str, phase_ids: list[str]
    ) -> RoadmapDocument:
        """Set a new phase order from the given id sequence."""
        ok = await self._repo.reorder_phases(roadmap_id, user_id, phase_ids)
        if not ok:
            raise NotFoundError(f"Roadmap '{roadmap_id}' not found")
        return await self._require(roadmap_id, user_id)

    async def _require(self, roadmap_id: str, user_id: str) -> RoadmapDocument:
        doc = await self._repo.get(roadmap_id, user_id)
        if doc is None:
            raise NotFoundError(f"Roadmap '{roadmap_id}' not found")
        return doc

    async def _prune_phase_progress(
        self, roadmap_id: str, user_id: str, phase_id: str, new_length: int
    ) -> None:
        """Drop completed keys for ``phase_id`` whose index is >= ``new_length``."""
        completed, _ = await self._repo.get_progress(roadmap_id, user_id)
        prefix = f"{phase_id}:"
        kept: list[str] = []
        for key in completed:
            if key.startswith(prefix):
                try:
                    idx = int(key[len(prefix):])
                except ValueError:
                    continue  # malformed — drop it
                if idx >= new_length:
                    continue  # out of range — drop it
            kept.append(key)
        if len(kept) != len(completed):
            await self._repo.set_progress(roadmap_id, user_id, kept)


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_roadmap_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> RoadmapService:
    """Injectable factory — wires FirestoreRoadmapRepository into RoadmapService."""
    from src.domains.roadmap.firestore_repository import FirestoreRoadmapRepository  # noqa: PLC0415

    return RoadmapService(FirestoreRoadmapRepository(db))
