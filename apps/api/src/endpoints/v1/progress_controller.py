"""Progress — weekly reviews and the career-health snapshot.

Routes:
  GET    /api/v1/progress/reviews   — list weekly reviews
  POST   /api/v1/progress/reviews   — submit a weekly review
  GET    /api/v1/progress/health    — get the career-health snapshot
  PUT    /api/v1/progress/health    — upsert the career-health snapshot
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.progress.schemas import (
    HealthSnapshotIn,
    HealthSnapshotOut,
    WeeklyReviewCreate,
    WeeklyReviewOut,
)
from src.domains.progress.service import ProgressService, get_progress_service

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/reviews", response_model=list[WeeklyReviewOut], summary="List weekly reviews")
async def list_reviews(
    limit: int = Query(default=26, ge=1, le=104),
    user: AuthenticatedUser = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> list[WeeklyReviewOut]:
    return await service.list_reviews(user.uid, limit=limit)


@router.post(
    "/reviews",
    response_model=WeeklyReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a weekly review",
)
async def create_review(
    body: WeeklyReviewCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> WeeklyReviewOut:
    return await service.create_review(user.uid, body)


@router.get("/health", response_model=HealthSnapshotOut, summary="Get career-health snapshot")
async def get_health(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> HealthSnapshotOut:
    return await service.get_health(user.uid)


@router.put("/health", response_model=HealthSnapshotOut, summary="Upsert career-health snapshot")
async def set_health(
    body: HealthSnapshotIn,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> HealthSnapshotOut:
    return await service.set_health(user.uid, body)
