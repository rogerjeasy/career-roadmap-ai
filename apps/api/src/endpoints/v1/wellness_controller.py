"""Wellness & Sustainability Monitor (§14.15).

Routes:
  GET    /api/v1/wellness/status         — current burnout-risk assessment
  GET    /api/v1/wellness/checkins       — recent check-ins
  POST   /api/v1/wellness/checkins       — log a check-in
  DELETE /api/v1/wellness/checkins/{id}  — remove a check-in
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.wellness.schemas import (
    WellnessCheckinCreate,
    WellnessCheckinOut,
    WellnessStatus,
)
from src.domains.wellness.service import WellnessService, get_wellness_service

router = APIRouter(prefix="/wellness", tags=["wellness"])


@router.get("/status", response_model=WellnessStatus, summary="Burnout-risk status")
async def get_status(
    user: AuthenticatedUser = Depends(get_current_user),
    service: WellnessService = Depends(get_wellness_service),
) -> WellnessStatus:
    return await service.status(user.uid)


@router.get("/checkins", response_model=list[WellnessCheckinOut], summary="Recent check-ins")
async def list_checkins(
    user: AuthenticatedUser = Depends(get_current_user),
    service: WellnessService = Depends(get_wellness_service),
) -> list[WellnessCheckinOut]:
    return await service.list_checkins(user.uid)


@router.post(
    "/checkins",
    response_model=WellnessCheckinOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log a wellness check-in",
)
async def create_checkin(
    payload: WellnessCheckinCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: WellnessService = Depends(get_wellness_service),
) -> WellnessCheckinOut:
    return await service.log_checkin(user.uid, payload)


@router.delete(
    "/checkins/{checkin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a check-in",
)
async def delete_checkin(
    checkin_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: WellnessService = Depends(get_wellness_service),
) -> None:
    await service.delete_checkin(user.uid, checkin_id)
