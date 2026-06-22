"""Personal Brand / Content Engine.

Routes:
  GET    /api/v1/content                 — my content drafts
  POST   /api/v1/content                 — generate a draft from milestones/context
  GET    /api/v1/content/{id}            — one draft
  PATCH  /api/v1/content/{id}/status     — approve / publish (consent-gated)
  DELETE /api/v1/content/{id}            — remove a draft
"""
from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.content.schemas import (
    ContentDraftOut,
    ContentGenerateInput,
    ContentStatusUpdate,
)
from src.domains.content.service import ContentService, get_content_service
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentDraftOut], summary="My content drafts")
async def list_drafts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContentService = Depends(get_content_service),
) -> list[ContentDraftOut]:
    return await service.list(user.uid)


@router.post(
    "",
    response_model=ContentDraftOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a content draft",
)
async def generate_draft(
    payload: ContentGenerateInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContentService = Depends(get_content_service),
) -> ContentDraftOut:
    return await service.generate(user.uid, payload)


@router.get("/{draft_id}", response_model=ContentDraftOut, summary="One draft")
async def get_draft(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContentService = Depends(get_content_service),
) -> ContentDraftOut:
    return await service.get(user.uid, draft_id)


@router.patch(
    "/{draft_id}/status",
    response_model=ContentDraftOut,
    summary="Approve or publish a draft (publishing is consent-gated)",
)
async def update_status(
    draft_id: str,
    payload: ContentStatusUpdate,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContentService = Depends(get_content_service),
    webhooks: WebhookService = Depends(get_webhook_service),
) -> ContentDraftOut:
    draft = await service.set_status(user.uid, draft_id, payload.status)
    if draft.status == "published":
        background.add_task(
            webhooks.dispatch,
            user.uid,
            "content.published",
            {"draft_id": draft.id, "kind": draft.kind},
        )
    return draft


@router.delete(
    "/{draft_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft"
)
async def delete_draft(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContentService = Depends(get_content_service),
) -> None:
    await service.delete(user.uid, draft_id)
