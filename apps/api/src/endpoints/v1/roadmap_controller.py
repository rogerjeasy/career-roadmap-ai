"""Roadmap endpoints — read and lifecycle management.

POST /roadmaps is intentionally absent: roadmaps are created exclusively
by the agent pipeline (Celery task → Firestore).  The API exposes only
read and soft-delete operations.

Routes:
  GET    /api/v1/roadmaps               — list user's roadmaps (summary only)
  GET    /api/v1/roadmaps/{roadmap_id}  — full roadmap with phases
  DELETE /api/v1/roadmaps/{roadmap_id}  — soft delete
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.domains.roadmap.schemas import RoadmapOut, RoadmapSummaryOut, RoadmapSummaryPage
from src.domains.roadmap.service import RoadmapService, get_roadmap_service

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])
logger = get_logger(__name__)


@router.get(
    "",
    response_model=list[RoadmapSummaryOut],
    summary="List roadmaps for the authenticated user",
)
async def list_roadmaps(
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapService = Depends(get_roadmap_service),
) -> list[RoadmapSummaryOut]:
    summaries = await service.list_for_user(user.uid, limit=limit)
    return [RoadmapSummaryOut.from_domain(s) for s in summaries]


@router.get(
    "/paginated",
    response_model=RoadmapSummaryPage,
    summary="Cursor-paginated roadmap list for infinite-scroll clients",
)
async def list_roadmaps_paginated(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, description="ISO-8601 created_at of last item"),
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapService = Depends(get_roadmap_service),
) -> RoadmapSummaryPage:
    summaries, next_cursor = await service.list_for_user_paginated(
        user.uid, limit=limit, cursor=cursor
    )
    return RoadmapSummaryPage(
        items=[RoadmapSummaryOut.from_domain(s) for s in summaries],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.get(
    "/{roadmap_id}",
    response_model=RoadmapOut,
    summary="Retrieve a roadmap with all phases, habits, and next steps",
)
async def get_roadmap(
    roadmap_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapService = Depends(get_roadmap_service),
) -> RoadmapOut:
    doc = await service.get(roadmap_id, user.uid)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roadmap not found",
        )
    logger.info("roadmap.fetched", roadmap_id=roadmap_id, user_id=user.uid)
    return RoadmapOut.from_domain(doc)


@router.delete(
    "/{roadmap_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a roadmap",
)
async def delete_roadmap(
    roadmap_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: RoadmapService = Depends(get_roadmap_service),
) -> None:
    try:
        await service.delete(roadmap_id, user.uid)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
