"""Exports — download a roadmap as Markdown or an iCalendar file.

Routes:
  GET    /api/v1/exports/roadmap/{id}/markdown   — text/markdown
  GET    /api/v1/exports/roadmap/{id}/ics        — text/calendar (.ics)
"""
from fastapi import APIRouter, Depends, Response

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.exports.service import ExportService, get_export_service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/roadmap/{roadmap_id}/markdown", summary="Roadmap as Markdown")
async def roadmap_markdown(
    roadmap_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> Response:
    body = await service.roadmap_markdown(user.uid, roadmap_id)
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="roadmap.md"'},
    )


@router.get("/roadmap/{roadmap_id}/ics", summary="Roadmap as iCalendar (.ics)")
async def roadmap_ics(
    roadmap_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> Response:
    body = await service.roadmap_ics(user.uid, roadmap_id)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="roadmap.ics"'},
    )
