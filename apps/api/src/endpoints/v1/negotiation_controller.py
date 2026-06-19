"""Negotiation & Offer Coach (§14.14).

Routes:
  POST   /api/v1/negotiation/analyze       — benchmark an offer + draft a counter
  GET    /api/v1/negotiation/offers        — my saved analyses
  GET    /api/v1/negotiation/offers/{id}   — one analysis
  DELETE /api/v1/negotiation/offers/{id}   — delete an analysis
  POST   /api/v1/negotiation/roleplay      — one recruiter roleplay turn + coaching
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.negotiation.schemas import (
    OfferAnalysisOut,
    OfferInput,
    RoleplayInput,
    RoleplayReply,
)
from src.domains.negotiation.service import (
    NegotiationService,
    get_negotiation_service,
)

router = APIRouter(prefix="/negotiation", tags=["negotiation"])


@router.post(
    "/analyze",
    response_model=OfferAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    summary="Benchmark an offer and draft a counter",
)
async def analyze_offer(
    payload: OfferInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NegotiationService = Depends(get_negotiation_service),
) -> OfferAnalysisOut:
    return await service.analyze(user.uid, payload)


@router.get("/offers", response_model=list[OfferAnalysisOut], summary="My analyses")
async def list_offers(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NegotiationService = Depends(get_negotiation_service),
) -> list[OfferAnalysisOut]:
    return await service.list(user.uid)


@router.get("/offers/{offer_id}", response_model=OfferAnalysisOut, summary="One analysis")
async def get_offer(
    offer_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NegotiationService = Depends(get_negotiation_service),
) -> OfferAnalysisOut:
    return await service.get(user.uid, offer_id)


@router.delete(
    "/offers/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an analysis",
)
async def delete_offer(
    offer_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NegotiationService = Depends(get_negotiation_service),
) -> None:
    await service.delete(user.uid, offer_id)


@router.post(
    "/roleplay",
    response_model=RoleplayReply,
    summary="One recruiter roleplay turn with private coaching",
)
async def roleplay(
    payload: RoleplayInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NegotiationService = Depends(get_negotiation_service),
) -> RoleplayReply:
    return await service.roleplay(user.uid, payload)
