"""Evidence Vault domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.evidence.firestore_repository import FirestoreEvidenceRepository
from src.domains.evidence.schemas import EvidenceCreate, EvidenceOut, EvidenceUpdate

logger = get_logger(__name__)


class EvidenceService:
    def __init__(self, repo: FirestoreEvidenceRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str, limit: int = 100) -> list[EvidenceOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [EvidenceOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, evidence_id: str) -> EvidenceOut:
        doc = await self._repo.get(evidence_id, user_id)
        if doc is None:
            raise NotFoundError(f"Evidence '{evidence_id}' not found")
        return EvidenceOut.from_doc(doc)

    async def create(self, user_id: str, payload: EvidenceCreate) -> EvidenceOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        return EvidenceOut.from_doc(doc)

    async def update(
        self, user_id: str, evidence_id: str, payload: EvidenceUpdate
    ) -> EvidenceOut:
        doc = await self._repo.update(evidence_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Evidence '{evidence_id}' not found")
        return EvidenceOut.from_doc(doc)

    async def delete(self, user_id: str, evidence_id: str) -> None:
        deleted = await self._repo.hard_delete(evidence_id, user_id)
        if not deleted:
            raise NotFoundError(f"Evidence '{evidence_id}' not found")


async def get_evidence_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> EvidenceService:
    return EvidenceService(FirestoreEvidenceRepository(db))
