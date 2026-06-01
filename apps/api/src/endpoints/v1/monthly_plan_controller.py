"""Monthly plan — monthly themes with weekly goal breakdowns.

Routes:
  GET    /api/v1/monthly-plans              — list plan summaries (oldest-first)
  PUT    /api/v1/monthly-plans              — create or update a plan (keyed by monthId)
  GET    /api/v1/monthly-plans/{month_id}   — get a full plan
  DELETE /api/v1/monthly-plans/{month_id}   — delete a plan
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.monthly_plan.schemas import (
    MonthlyPlanOut,
    MonthlyPlanSummaryOut,
    MonthlyPlanUpsert,
)
from src.domains.monthly_plan.service import (
    MonthlyPlanService,
    get_monthly_plan_service,
)

router = APIRouter(prefix="/monthly-plans", tags=["monthly-plans"])


@router.get("", response_model=list[MonthlyPlanSummaryOut], summary="List monthly plans")
async def list_plans(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MonthlyPlanService = Depends(get_monthly_plan_service),
) -> list[MonthlyPlanSummaryOut]:
    return await service.list(user.uid)


@router.put("", response_model=MonthlyPlanOut, summary="Create or update a monthly plan")
async def upsert_plan(
    body: MonthlyPlanUpsert,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MonthlyPlanService = Depends(get_monthly_plan_service),
) -> MonthlyPlanOut:
    return await service.upsert(user.uid, body)


@router.get("/{month_id}", response_model=MonthlyPlanOut, summary="Get a monthly plan")
async def get_plan(
    month_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MonthlyPlanService = Depends(get_monthly_plan_service),
) -> MonthlyPlanOut:
    return await service.get(user.uid, month_id)


@router.delete(
    "/{month_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a monthly plan",
)
async def delete_plan(
    month_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MonthlyPlanService = Depends(get_monthly_plan_service),
) -> None:
    await service.delete(user.uid, month_id)
