"""Career Storytelling Studio (§14.19).

Routes:
  POST   /api/v1/storytelling/generate     — generate a narrative from evidence
  GET    /api/v1/storytelling/drafts       — my saved drafts
  GET    /api/v1/storytelling/drafts/{id}  — one draft
  DELETE /api/v1/storytelling/drafts/{id}  — delete a draft
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.storytelling.schemas import StoryDraftOut, StoryGenerateInput
from src.domains.storytelling.service import (
    StorytellingService,
    get_storytelling_service,
)

router = APIRouter(prefix="/storytelling", tags=["storytelling"])


@router.post(
    "/generate",
    response_model=StoryDraftOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a narrative from selected evidence",
)
async def generate_story(
    payload: StoryGenerateInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: StorytellingService = Depends(get_storytelling_service),
) -> StoryDraftOut:
    return await service.generate(user.uid, payload)


@router.get("/drafts", response_model=list[StoryDraftOut], summary="My drafts")
async def list_drafts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: StorytellingService = Depends(get_storytelling_service),
) -> list[StoryDraftOut]:
    return await service.list_drafts(user.uid)


@router.get("/drafts/{draft_id}", response_model=StoryDraftOut, summary="One draft")
async def get_draft(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: StorytellingService = Depends(get_storytelling_service),
) -> StoryDraftOut:
    return await service.get_draft(user.uid, draft_id)


@router.delete(
    "/drafts/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft",
)
async def delete_draft(
    draft_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: StorytellingService = Depends(get_storytelling_service),
) -> None:
    await service.delete_draft(user.uid, draft_id)
