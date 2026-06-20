"""Roadmap Strategy Options (§9).

Routes:
  GET    /api/v1/roadmap-options             — latest generated strategy set
  POST   /api/v1/roadmap-options/generate    — generate aggressive/balanced/long-term
  POST   /api/v1/roadmap-options/select      — choose a strategy
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.roadmap_options.schemas import RoadmapOptionsSet, SelectStrategyInput
from src.domains.roadmap_options.service import (
    RoadmapOptionsService,
    get_roadmap_options_service,
)

router = APIRouter(prefix="/roadmap-options", tags=["roadmap-options"])


@router.get("", response_model=RoadmapOptionsSet, summary="Latest strategy options")
async def get_options(
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapOptionsService = Depends(get_roadmap_options_service),
) -> RoadmapOptionsSet:
    return await service.get(user.uid)


@router.post(
    "/generate", response_model=RoadmapOptionsSet, summary="Generate three strategies"
)
async def generate_options(
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapOptionsService = Depends(get_roadmap_options_service),
) -> RoadmapOptionsSet:
    return await service.generate(user.uid)


@router.post("/select", response_model=RoadmapOptionsSet, summary="Select a strategy")
async def select_option(
    payload: SelectStrategyInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapOptionsService = Depends(get_roadmap_options_service),
) -> RoadmapOptionsSet:
    return await service.select(user.uid, payload.strategy)
