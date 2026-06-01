"""Networking domain — service layer for contacts, events, and outreach."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.networking.firestore_repository import (
    FirestoreContactRepository,
    FirestoreEventRepository,
    FirestoreOutreachRepository,
)
from src.domains.networking.schemas import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    EventCreate,
    EventOut,
    OutreachCreate,
    OutreachOut,
)

logger = get_logger(__name__)


class NetworkingService:
    def __init__(
        self,
        contacts: FirestoreContactRepository,
        events: FirestoreEventRepository,
        outreach: FirestoreOutreachRepository,
    ) -> None:
        self._contacts = contacts
        self._events = events
        self._outreach = outreach

    # ── Contacts ──────────────────────────────────────────────────────────────

    async def list_contacts(self, user_id: str) -> list[ContactOut]:
        docs = await self._contacts.list_for_user(user_id, limit=200)
        return [ContactOut.from_doc(d) for d in docs]

    async def create_contact(self, user_id: str, payload: ContactCreate) -> ContactOut:
        doc = await self._contacts.create(user_id, payload.model_dump())
        return ContactOut.from_doc(doc)

    async def update_contact(self, user_id: str, contact_id: str, payload: ContactUpdate) -> ContactOut:
        doc = await self._contacts.update(contact_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Contact '{contact_id}' not found")
        return ContactOut.from_doc(doc)

    async def delete_contact(self, user_id: str, contact_id: str) -> None:
        if not await self._contacts.hard_delete(contact_id, user_id):
            raise NotFoundError(f"Contact '{contact_id}' not found")

    # ── Events ────────────────────────────────────────────────────────────────

    async def list_events(self, user_id: str) -> list[EventOut]:
        docs = await self._events.list_for_user(user_id, limit=200, order_desc=False)
        return [EventOut.from_doc(d) for d in docs]

    async def create_event(self, user_id: str, payload: EventCreate) -> EventOut:
        doc = await self._events.create(user_id, payload.model_dump())
        return EventOut.from_doc(doc)

    async def delete_event(self, user_id: str, event_id: str) -> None:
        if not await self._events.hard_delete(event_id, user_id):
            raise NotFoundError(f"Event '{event_id}' not found")

    # ── Outreach log ──────────────────────────────────────────────────────────

    async def list_outreach(self, user_id: str, limit: int = 50) -> list[OutreachOut]:
        docs = await self._outreach.list_for_user(user_id, limit=limit)
        return [OutreachOut.from_doc(d) for d in docs]

    async def log_outreach(self, user_id: str, payload: OutreachCreate) -> OutreachOut:
        doc = await self._outreach.create(user_id, payload.model_dump())
        return OutreachOut.from_doc(doc)


async def get_networking_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> NetworkingService:
    return NetworkingService(
        FirestoreContactRepository(db),
        FirestoreEventRepository(db),
        FirestoreOutreachRepository(db),
    )
