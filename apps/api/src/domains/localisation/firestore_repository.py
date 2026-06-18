"""Localisation domain — Firestore repository (collection: ``localisation_reports``).

Reports are cached per user with a deterministic doc id (``report_slug``) so a
repeat lookup for the same (country, role) reuses the cached report instead of
re-calling the LLM.
"""
from __future__ import annotations

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreLocalisationRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "localisation_reports")
