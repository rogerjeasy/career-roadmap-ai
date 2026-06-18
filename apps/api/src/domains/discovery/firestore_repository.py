"""Discovery domain — Firestore repository (collection: ``discovery_results``).

One document per user (doc id == ``user_id``) holds the latest discovery run.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreDiscoveryRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "discovery_results")
