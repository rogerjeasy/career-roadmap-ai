"""Contact domain — service layer.

Public, create-only: a marketing-site visitor files an enquiry and we store it
for the team to triage. There is no per-user scope (the sender isn't logged in),
so the submitted email doubles as the document's owner key — keeping it
compatible with the shared user-scoped CRUD base and queryable by sender.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.contact.firestore_repository import FirestoreContactRepository
from src.domains.contact.schemas import ContactRequestAck, ContactRequestCreate

logger = get_logger(__name__)


class ContactService:
    def __init__(self, repo: FirestoreContactRepository) -> None:
        self._repo = repo

    async def submit(self, payload: ContactRequestCreate) -> ContactRequestAck:
        owner = payload.email.lower()
        doc = await self._repo.create(owner, payload.model_dump(mode="json"))
        logger.info(
            "contact.submitted",
            contact_id=doc["id"],
            email=owner,
            topic=payload.topic,
        )
        return ContactRequestAck()


async def get_contact_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> ContactService:
    return ContactService(FirestoreContactRepository(db))
