"""Localisation — country-aware career intelligence (Global Localisation Engine).

Routes:
  GET    /api/v1/localisation         — report for a country (role from session if omitted)
  GET    /api/v1/localisation/saved   — previously generated reports
  DELETE /api/v1/localisation/{id}    — remove a saved report

The compare view in the UI is built by calling GET twice with different
countries — each side is an independently cached report.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.localisation.schemas import (
    LocalisationReport,
    LocalisationReportSummary,
)
from src.domains.localisation.service import (
    LocalisationService,
    get_localisation_service,
)
from src.session.manager import SessionManager, get_session_manager

router = APIRouter(prefix="/localisation", tags=["localisation"])


async def _resolve_role(
    role: str | None, user: AuthenticatedUser, mgr: SessionManager
) -> str:
    """Use the explicit role, else the session's target role."""
    if role and role.strip():
        return role.strip()
    session = await mgr.get(user.uid)
    profile = session.user_profile_context if session else None
    target = (profile.target_role if profile else None) or (
        profile.current_role if profile else None
    )
    if target and target.strip():
        return target.strip()
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="No target role found. Pass ?role= or set a target role in your profile first.",
    )


@router.get("", response_model=LocalisationReport, summary="Country-aware career report")
async def get_localisation(
    country: str = Query(min_length=1, max_length=120),
    role: str | None = Query(default=None, max_length=160),
    refresh: bool = Query(default=False),
    user: AuthenticatedUser = Depends(get_current_user),
    service: LocalisationService = Depends(get_localisation_service),
    mgr: SessionManager = Depends(get_session_manager),
) -> LocalisationReport:
    resolved_role = await _resolve_role(role, user, mgr)
    return await service.get_report(user.uid, country, resolved_role, refresh=refresh)


@router.get(
    "/saved",
    response_model=list[LocalisationReportSummary],
    summary="List previously generated reports",
)
async def list_saved(
    user: AuthenticatedUser = Depends(get_current_user),
    service: LocalisationService = Depends(get_localisation_service),
) -> list[LocalisationReportSummary]:
    return await service.list_saved(user.uid)


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved report",
)
async def delete_report(
    report_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: LocalisationService = Depends(get_localisation_service),
) -> None:
    deleted = await service.delete(user.uid, report_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found."
        )
