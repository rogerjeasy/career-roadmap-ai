"""Web Push — Firestore repository (collection: ``push_subscriptions``).

One document per device, keyed by a stable hash of the endpoint so re-subscribing
the same device updates rather than duplicates.
"""
from __future__ import annotations

import hashlib

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


def device_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:32]


class FirestorePushRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "push_subscriptions")
