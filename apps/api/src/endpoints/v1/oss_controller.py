"""Open-Source Contribution Finder (§14.18).

Routes:
  GET    /api/v1/oss/issues               — live GitHub good-first-issue search
  GET    /api/v1/oss/bookmarks            — my saved issues
  POST   /api/v1/oss/bookmarks            — bookmark an issue
  PATCH  /api/v1/oss/bookmarks/{id}       — update a bookmark's status
  DELETE /api/v1/oss/bookmarks/{id}       — remove a bookmark
"""
from fastapi import APIRouter, Body, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.oss.schemas import (
    OssBookmarkCreate,
    OssBookmarkOut,
    OssSearchResult,
)
from src.domains.oss.service import OssService, get_oss_service

router = APIRouter(prefix="/oss", tags=["oss"])


@router.get("/issues", response_model=OssSearchResult, summary="Search good-first-issues")
async def search_issues(
    language: str | None = Query(default=None, max_length=60),
    query: str | None = Query(default=None, max_length=200),
    user: AuthenticatedUser = Depends(get_current_user),
    service: OssService = Depends(get_oss_service),
) -> OssSearchResult:
    return await service.search(user.uid, language, query)


@router.get("/bookmarks", response_model=list[OssBookmarkOut], summary="My bookmarks")
async def list_bookmarks(
    user: AuthenticatedUser = Depends(get_current_user),
    service: OssService = Depends(get_oss_service),
) -> list[OssBookmarkOut]:
    return await service.list_bookmarks(user.uid)


@router.post(
    "/bookmarks",
    response_model=OssBookmarkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Bookmark an issue",
)
async def add_bookmark(
    payload: OssBookmarkCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OssService = Depends(get_oss_service),
) -> OssBookmarkOut:
    return await service.add_bookmark(user.uid, payload)


@router.patch(
    "/bookmarks/{bookmark_id}", response_model=OssBookmarkOut, summary="Update status"
)
async def update_bookmark(
    bookmark_id: str,
    status_value: str = Body(..., embed=True, alias="status", max_length=30),
    user: AuthenticatedUser = Depends(get_current_user),
    service: OssService = Depends(get_oss_service),
) -> OssBookmarkOut:
    return await service.update_bookmark_status(user.uid, bookmark_id, status_value)


@router.delete(
    "/bookmarks/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a bookmark",
)
async def remove_bookmark(
    bookmark_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: OssService = Depends(get_oss_service),
) -> None:
    await service.remove_bookmark(user.uid, bookmark_id)
