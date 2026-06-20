"""Analytics — cross-feature insight dashboard.

Routes:
  GET    /api/v1/analytics/overview   — aggregated metrics across the platform
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.analytics.schemas import AnalyticsOverview
from src.domains.analytics.service import AnalyticsService, get_analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview, summary="Analytics overview")
async def overview(
    user: AuthenticatedUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverview:
    return await service.overview(user.uid)
