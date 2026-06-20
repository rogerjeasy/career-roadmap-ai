"""Plan Version Snapshots — Firestore repository (collection: ``roadmap_snapshots``)."""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreSnapshotRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "roadmap_snapshots")
