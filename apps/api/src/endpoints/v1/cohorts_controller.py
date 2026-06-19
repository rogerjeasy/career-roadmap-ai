"""Accountability Cohorts (§14.12).

Routes:
  GET    /api/v1/cohorts                      — cohorts I'm a member of
  GET    /api/v1/cohorts/discover             — open cohorts ranked by goal match
  POST   /api/v1/cohorts                      — create a cohort
  GET    /api/v1/cohorts/{id}                 — member dashboard (cohort + check-ins)
  POST   /api/v1/cohorts/{id}/join            — join a cohort
  POST   /api/v1/cohorts/{id}/leave           — leave a cohort
  POST   /api/v1/cohorts/{id}/checkins        — post a check-in
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.cohorts.schemas import (
    CheckinCreate,
    CheckinOut,
    CohortCreate,
    CohortDashboard,
    CohortOut,
)
from src.domains.cohorts.service import CohortService, get_cohort_service

router = APIRouter(prefix="/cohorts", tags=["cohorts"])


def _name(user: AuthenticatedUser) -> str:
    return user.name or (user.email.split("@")[0] if user.email else "A member")


@router.get("", response_model=list[CohortOut], summary="My cohorts")
async def list_my_cohorts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> list[CohortOut]:
    return await service.list_mine(user.uid)


@router.get("/discover", response_model=list[CohortOut], summary="Discover open cohorts")
async def discover_cohorts(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> list[CohortOut]:
    return await service.discover(user.uid)


@router.post(
    "",
    response_model=CohortOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cohort",
)
async def create_cohort(
    payload: CohortCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> CohortOut:
    return await service.create(user.uid, _name(user), payload)


@router.get("/{cohort_id}", response_model=CohortDashboard, summary="Cohort dashboard")
async def get_dashboard(
    cohort_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> CohortDashboard:
    return await service.dashboard(user.uid, cohort_id)


@router.post("/{cohort_id}/join", response_model=CohortOut, summary="Join a cohort")
async def join_cohort(
    cohort_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> CohortOut:
    return await service.join(user.uid, _name(user), cohort_id)


@router.post(
    "/{cohort_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave a cohort",
)
async def leave_cohort(
    cohort_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> None:
    await service.leave(user.uid, cohort_id)


@router.post(
    "/{cohort_id}/checkins",
    response_model=CheckinOut,
    status_code=status.HTTP_201_CREATED,
    summary="Post a check-in",
)
async def post_checkin(
    cohort_id: str,
    payload: CheckinCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CohortService = Depends(get_cohort_service),
) -> CheckinOut:
    return await service.post_checkin(user.uid, _name(user), cohort_id, payload)
