"""Market — cached market intelligence for the user's target role.

GET /api/v1/market/overview
    Returns the most recent market signals, salary benchmark, and trending
    skills cached in the session plan context. Returns empty lists with
    ``hasData=false`` when no market run has produced data yet.
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.market.schemas import MarketOverviewOut
from src.domains.market.service import MarketService, get_market_service

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewOut, summary="Get market overview")
async def get_market_overview(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MarketService = Depends(get_market_service),
) -> MarketOverviewOut:
    return await service.get_overview(user.uid)
