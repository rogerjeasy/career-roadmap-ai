"""Learning ROI Tracker (§14.11).

Routes:
  GET    /api/v1/learning                 — items ranked by expected ROI
  GET    /api/v1/learning/summary         — portfolio-level rollup
  POST   /api/v1/learning                 — log a learning investment
  PATCH  /api/v1/learning/{id}            — update an item
  DELETE /api/v1/learning/{id}            — remove an item
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.learning_roi.schemas import (
    LearningItemCreate,
    LearningItemOut,
    LearningItemUpdate,
    LearningRoiSummary,
)
from src.domains.learning_roi.service import (
    LearningRoiService,
    get_learning_roi_service,
)

router = APIRouter(prefix="/learning", tags=["learning-roi"])


@router.get("", response_model=list[LearningItemOut], summary="Items ranked by ROI")
async def list_items(
    user: AuthenticatedUser = Depends(get_current_user),
    service: LearningRoiService = Depends(get_learning_roi_service),
) -> list[LearningItemOut]:
    return await service.list_ranked(user.uid)


@router.get("/summary", response_model=LearningRoiSummary, summary="Portfolio rollup")
async def get_summary(
    user: AuthenticatedUser = Depends(get_current_user),
    service: LearningRoiService = Depends(get_learning_roi_service),
) -> LearningRoiSummary:
    return await service.summary(user.uid)


@router.post(
    "",
    response_model=LearningItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log a learning investment",
)
async def create_item(
    payload: LearningItemCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: LearningRoiService = Depends(get_learning_roi_service),
) -> LearningItemOut:
    return await service.create(user.uid, payload)


@router.patch("/{item_id}", response_model=LearningItemOut, summary="Update an item")
async def update_item(
    item_id: str,
    payload: LearningItemUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: LearningRoiService = Depends(get_learning_roi_service),
) -> LearningItemOut:
    return await service.update(user.uid, item_id, payload)


@router.delete(
    "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an item"
)
async def delete_item(
    item_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: LearningRoiService = Depends(get_learning_roi_service),
) -> None:
    await service.delete(user.uid, item_id)
