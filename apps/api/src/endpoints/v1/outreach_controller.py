"""AI Outreach Drafting (human-approval gate).

Routes:
  GET    /api/v1/outreach              — my drafts
  POST   /api/v1/outreach/draft        — draft a message (LLM)
  PATCH  /api/v1/outreach/{id}         — edit (reverts to draft)
  POST   /api/v1/outreach/{id}/approve — approve a draft
  POST   /api/v1/outreach/{id}/sent    — mark an approved draft as sent
  DELETE /api/v1/outreach/{id}         — delete a draft
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.outreach.schemas import (
    OutreachDraftOut,
    OutreachDraftRequest,
    OutreachEdit,
)
from src.domains.outreach.service import OutreachService, get_outreach_service

router = APIRouter(prefix="/outreach", tags=["outreach"])


@router.get("", response_model=list[OutreachDraftOut], summary="My outreach drafts")
async def list_drafts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> list[OutreachDraftOut]:
    return await service.list(user.uid)


@router.post(
    "/draft",
    response_model=OutreachDraftOut,
    status_code=status.HTTP_201_CREATED,
    summary="Draft a message",
)
async def draft(
    payload: OutreachDraftRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> OutreachDraftOut:
    return await service.draft(user.uid, payload)


@router.patch("/{draft_id}", response_model=OutreachDraftOut, summary="Edit a draft")
async def edit(
    draft_id: str,
    payload: OutreachEdit,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> OutreachDraftOut:
    return await service.edit(user.uid, draft_id, payload)


@router.post("/{draft_id}/approve", response_model=OutreachDraftOut, summary="Approve")
async def approve(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> OutreachDraftOut:
    return await service.approve(user.uid, draft_id)


@router.post("/{draft_id}/sent", response_model=OutreachDraftOut, summary="Mark as sent")
async def mark_sent(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> OutreachDraftOut:
    return await service.mark_sent(user.uid, draft_id)


@router.delete(
    "/{draft_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft"
)
async def delete(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OutreachService = Depends(get_outreach_service),
) -> None:
    await service.delete(user.uid, draft_id)
