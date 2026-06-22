"""Portfolio Build Plan — AI-guided artefact sequencing (§14.7).

Registered BEFORE the portfolio CRUD router so the literal ``/portfolio/plan``
path matches ahead of ``/portfolio/{item_id}``.

Routes:
  GET    /api/v1/portfolio/plan            — latest build plan
  POST   /api/v1/portfolio/plan/generate   — (re)generate the prioritised plan
  POST   /api/v1/portfolio/plan/track      — track a suggestion (portfolio + schedule)
"""
from pydantic import BaseModel

from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.portfolio.plan_schemas import PlanTrackResult, PortfolioPlan
from src.domains.portfolio.planner import (
    PortfolioPlannerService,
    get_portfolio_planner_service,
)

router = APIRouter(prefix="/portfolio/plan", tags=["portfolio"])


class PlanTrackRequest(BaseModel):
    suggestion_id: str


@router.get("", response_model=PortfolioPlan, summary="Latest portfolio build plan")
async def get_plan(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioPlannerService = Depends(get_portfolio_planner_service),
) -> PortfolioPlan:
    return await service.get(user.uid)


@router.post(
    "/generate", response_model=PortfolioPlan, summary="Generate the build plan"
)
async def generate_plan(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioPlannerService = Depends(get_portfolio_planner_service),
) -> PortfolioPlan:
    return await service.generate(user.uid)


@router.post(
    "/track",
    response_model=PlanTrackResult,
    summary="Track a suggestion as portfolio + schedule work",
)
async def track_suggestion(
    payload: PlanTrackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioPlannerService = Depends(get_portfolio_planner_service),
) -> PlanTrackResult:
    return await service.track(user.uid, payload.suggestion_id)
