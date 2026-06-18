"""Career discovery — comparable career paths derived from the user's CV/profile.

Routes:
  GET  /api/v1/discovery           — latest cached discovery result (empty if none)
  POST /api/v1/discovery/generate  — (re)generate paths from the current profile
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.discovery.schemas import DiscoveryResult
from src.domains.discovery.service import DiscoveryService, get_discovery_service

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("", response_model=DiscoveryResult, summary="Latest career-path discovery")
async def get_discovery(
    user: AuthenticatedUser = Depends(get_current_user),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    return await service.get(user.uid)


@router.post(
    "/generate",
    response_model=DiscoveryResult,
    summary="Generate career paths from the current profile",
)
async def generate_discovery(
    user: AuthenticatedUser = Depends(get_current_user),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    return await service.generate(user.uid)
