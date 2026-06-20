"""Roadmap Strategy Options — Firestore repository (collection: ``roadmap_options``).

One document per user (doc id == user_id); ``generate`` overwrites the prior set.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreRoadmapOptionsRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "roadmap_options")
