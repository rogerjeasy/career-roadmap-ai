"""Plan Version Snapshots — service layer.

Captures and restores full roadmap snapshots. Restore is itself undoable: the
current roadmap is auto-snapshotted before being overwritten. All reads/writes
are owner-scoped and a snapshot may only be restored onto a roadmap the caller
still owns.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.roadmap.firestore_repository import FirestoreRoadmapRepository
from src.domains.roadmap.schemas import RoadmapDocument
from src.domains.snapshots.firestore_repository import FirestoreSnapshotRepository
from src.domains.snapshots.schemas import SnapshotOut

logger = get_logger(__name__)

_MAX_SNAPSHOTS = 25  # per roadmap; oldest auto-snapshots are pruned beyond this


class SnapshotService:
    def __init__(
        self,
        repo: FirestoreSnapshotRepository,
        roadmaps: FirestoreRoadmapRepository,
    ) -> None:
        self._repo = repo
        self._roadmaps = roadmaps

    async def list(self, user_id: str, roadmap_id: str) -> list[SnapshotOut]:
        docs = await self._repo.list_for_user(user_id, limit=200)
        return [
            SnapshotOut.from_doc(d) for d in docs if d.get("roadmap_id") == roadmap_id
        ]

    async def create(
        self, user_id: str, roadmap_id: str, label: str, *, auto: bool = False
    ) -> SnapshotOut:
        doc = await self._roadmaps.get(roadmap_id, user_id)
        if doc is None:
            raise NotFoundError("Roadmap not found.")
        payload = {
            "roadmap_id": roadmap_id,
            "label": label or ("Auto-saved before restore" if auto else "Manual snapshot"),
            "summary": doc.summary,
            "phase_count": len(doc.phases),
            "auto": auto,
            "snapshot": doc.model_dump(),
        }
        created = await self._repo.create(user_id, payload)
        await self._prune(user_id, roadmap_id)
        logger.info("snapshot.created", user_id=user_id, roadmap_id=roadmap_id, auto=auto)
        return SnapshotOut.from_doc(created)

    async def restore(self, user_id: str, snapshot_id: str) -> SnapshotOut:
        snap = await self._repo.get(snapshot_id, user_id)
        if snap is None:
            raise NotFoundError("Snapshot not found.")
        roadmap_id = snap.get("roadmap_id", "")

        # Verify the target roadmap still belongs to the caller before overwriting.
        current = await self._roadmaps.get(roadmap_id, user_id)
        if current is None:
            raise NotFoundError("The roadmap this snapshot belongs to no longer exists.")

        # Auto-snapshot the current state so the restore is itself undoable.
        await self.create(user_id, roadmap_id, "Auto-saved before restore", auto=True)

        raw = snap.get("snapshot") or {}
        restored = RoadmapDocument.model_validate(raw)
        await self._roadmaps.restore_in_place(restored)
        logger.info("snapshot.restored", user_id=user_id, snapshot_id=snapshot_id)
        return SnapshotOut.from_doc(snap)

    async def delete(self, user_id: str, snapshot_id: str) -> None:
        removed = await self._repo.hard_delete(snapshot_id, user_id)
        if not removed:
            raise NotFoundError("Snapshot not found.")

    async def _prune(self, user_id: str, roadmap_id: str) -> None:
        docs = [
            d
            for d in await self._repo.list_for_user(user_id, limit=200)
            if d.get("roadmap_id") == roadmap_id
        ]
        if len(docs) <= _MAX_SNAPSHOTS:
            return
        # list_for_user is newest-first; prune the oldest beyond the cap.
        for d in docs[_MAX_SNAPSHOTS:]:
            try:
                await self._repo.hard_delete(d["id"], user_id)
            except Exception:  # noqa: BLE001 — pruning is best-effort
                pass


async def get_snapshot_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> SnapshotService:
    return SnapshotService(
        FirestoreSnapshotRepository(db),
        FirestoreRoadmapRepository(db),
    )
