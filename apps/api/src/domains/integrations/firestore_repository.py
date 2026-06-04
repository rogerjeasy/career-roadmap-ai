"""Integrations domain — Firestore repository.

One document per (user, provider) in the ``user_integrations`` collection, keyed
by ``{user_id}:{provider}`` so a user can have at most one active connection per
provider. OAuth tokens are stored encrypted (see ``crypto.py``).
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreIntegrationRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "user_integrations")

    @staticmethod
    def doc_id(user_id: str, provider: str) -> str:
        return f"{user_id}:{provider}"
