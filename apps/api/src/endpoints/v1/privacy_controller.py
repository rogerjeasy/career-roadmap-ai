"""Privacy — data export + account deletion (Responsible AI controls).

Routes:
  GET    /api/v1/privacy/export    — download all my data as JSON
  POST   /api/v1/privacy/purge     — erase my feature data (keep the account)
  DELETE /api/v1/privacy/account   — erase data AND delete the account (irreversible)
"""
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.privacy.service import PrivacyService, get_privacy_service

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/export", summary="Export all my data as JSON")
async def export_data(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PrivacyService = Depends(get_privacy_service),
) -> dict[str, Any]:
    bundle = await service.export(user.uid)
    return bundle


@router.post("/purge", summary="Erase my feature data (keep account)")
async def purge_data(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PrivacyService = Depends(get_privacy_service),
) -> dict[str, int]:
    removed = await service.purge_data(user.uid)
    return {"removed": removed}


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete account and all data (irreversible)",
)
async def delete_account(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PrivacyService = Depends(get_privacy_service),
) -> Response:
    await service.delete_account(user.uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
