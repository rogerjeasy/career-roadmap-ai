"""Networking domain — Firestore repositories.

Collections: ``contacts``, ``networking_events``, ``outreach_log``.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreContactRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "contacts")


class FirestoreEventRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "networking_events")


class FirestoreOutreachRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "outreach_log")
