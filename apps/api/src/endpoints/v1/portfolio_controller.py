"""Portfolio — CRUD for the user's project showcase.

Routes:
  GET    /api/v1/portfolio          — list projects (newest-first)
  POST   /api/v1/portfolio          — add a project
  GET    /api/v1/portfolio/{id}     — get one
  PATCH  /api/v1/portfolio/{id}     — update one
  DELETE /api/v1/portfolio/{id}     — remove one
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.portfolio.schemas import (
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
)
from src.domains.portfolio.service import PortfolioService, get_portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioItemOut], summary="List portfolio items")
async def list_portfolio(
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[PortfolioItemOut]:
    return await service.list(user.uid, limit=limit)


@router.post(
    "",
    response_model=PortfolioItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a portfolio item",
)
async def create_portfolio_item(
    body: PortfolioItemCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioItemOut:
    return await service.create(user.uid, body)


@router.get(
    "/{item_id}", response_model=PortfolioItemOut, summary="Get a portfolio item"
)
async def get_portfolio_item(
    item_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioItemOut:
    return await service.get(user.uid, item_id)


@router.patch(
    "/{item_id}", response_model=PortfolioItemOut, summary="Update a portfolio item"
)
async def update_portfolio_item(
    item_id: str,
    body: PortfolioItemUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioItemOut:
    return await service.update(user.uid, item_id, body)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a portfolio item",
)
async def delete_portfolio_item(
    item_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> None:
    await service.delete(user.uid, item_id)
