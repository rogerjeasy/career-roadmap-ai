"""Autopilot — surfaces consent-gated plan-adjustment proposals.

Routes:
  GET    /api/v1/autopilot                  — open proposals
  POST   /api/v1/autopilot/refresh          — recompute from current signals
  POST   /api/v1/autopilot/{id}/accept      — mark a proposal accepted
  POST   /api/v1/autopilot/{id}/dismiss     — mark a proposal dismissed
"""
from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.autopilot.schemas import AutopilotProposalOut
from src.domains.autopilot.service import AutopilotService, get_autopilot_service

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.get("", response_model=list[AutopilotProposalOut], summary="Open proposals")
async def list_proposals(
    user: AuthenticatedUser = Depends(get_current_user),
    service: AutopilotService = Depends(get_autopilot_service),
) -> list[AutopilotProposalOut]:
    return await service.list_open(user.uid)


@router.post(
    "/refresh",
    response_model=list[AutopilotProposalOut],
    summary="Recompute proposals from current signals",
)
async def refresh_proposals(
    user: AuthenticatedUser = Depends(get_current_user),
    service: AutopilotService = Depends(get_autopilot_service),
) -> list[AutopilotProposalOut]:
    return await service.refresh(user.uid)


@router.post(
    "/{proposal_id}/accept",
    response_model=AutopilotProposalOut,
    summary="Accept a proposal",
)
async def accept_proposal(
    proposal_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AutopilotService = Depends(get_autopilot_service),
) -> AutopilotProposalOut:
    out = await service.set_status(user.uid, proposal_id, "accepted")
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found.")
    return out


@router.post(
    "/{proposal_id}/dismiss",
    response_model=AutopilotProposalOut,
    summary="Dismiss a proposal",
)
async def dismiss_proposal(
    proposal_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AutopilotService = Depends(get_autopilot_service),
) -> AutopilotProposalOut:
    out = await service.set_status(user.uid, proposal_id, "dismissed")
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found.")
    return out
