"""Networking — contacts, events, and outreach log.

Routes:
  GET    /api/v1/networking/contacts        — list contacts
  POST   /api/v1/networking/contacts        — add a contact
  PATCH  /api/v1/networking/contacts/{id}   — update a contact
  DELETE /api/v1/networking/contacts/{id}   — delete a contact
  GET    /api/v1/networking/events          — list events
  POST   /api/v1/networking/events          — add an event
  DELETE /api/v1/networking/events/{id}     — delete an event
  GET    /api/v1/networking/outreach        — list outreach log
  POST   /api/v1/networking/outreach        — log an outreach
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.networking.schemas import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    EventCreate,
    EventOut,
    OutreachCreate,
    OutreachOut,
)
from src.domains.networking.service import NetworkingService, get_networking_service

router = APIRouter(prefix="/networking", tags=["networking"])


# ── Contacts ──────────────────────────────────────────────────────────────────

@router.get("/contacts", response_model=list[ContactOut], summary="List contacts")
async def list_contacts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> list[ContactOut]:
    return await service.list_contacts(user.uid)


@router.post(
    "/contacts",
    response_model=ContactOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a contact",
)
async def create_contact(
    body: ContactCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> ContactOut:
    return await service.create_contact(user.uid, body)


@router.patch("/contacts/{contact_id}", response_model=ContactOut, summary="Update a contact")
async def update_contact(
    contact_id: str,
    body: ContactUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> ContactOut:
    return await service.update_contact(user.uid, contact_id, body)


@router.delete(
    "/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact",
)
async def delete_contact(
    contact_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> None:
    await service.delete_contact(user.uid, contact_id)


# ── Events ────────────────────────────────────────────────────────────────────

@router.get("/events", response_model=list[EventOut], summary="List events")
async def list_events(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> list[EventOut]:
    return await service.list_events(user.uid)


@router.post(
    "/events",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an event",
)
async def create_event(
    body: EventCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> EventOut:
    return await service.create_event(user.uid, body)


@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event",
)
async def delete_event(
    event_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> None:
    await service.delete_event(user.uid, event_id)


# ── Outreach log ──────────────────────────────────────────────────────────────

@router.get("/outreach", response_model=list[OutreachOut], summary="List outreach log")
async def list_outreach(
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> list[OutreachOut]:
    return await service.list_outreach(user.uid, limit=limit)


@router.post(
    "/outreach",
    response_model=OutreachOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log an outreach",
)
async def log_outreach(
    body: OutreachCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NetworkingService = Depends(get_networking_service),
) -> OutreachOut:
    return await service.log_outreach(user.uid, body)
