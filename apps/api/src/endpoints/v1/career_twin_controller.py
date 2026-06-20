"""Career Twin / Digital Twin (§14.1).

Routes:
  GET    /api/v1/career-twin/persona        — my twin's persona
  PUT    /api/v1/career-twin/persona        — configure the persona
  GET    /api/v1/career-twin/today          — today's check-in (created lazily)
  POST   /api/v1/career-twin/{id}/reply     — answer a check-in; twin responds
  GET    /api/v1/career-twin/history        — check-in journal
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.career_twin.schemas import (
    CheckinReply,
    DailyCheckinOut,
    TwinPersonaOut,
    TwinPersonaUpsert,
)
from src.domains.career_twin.service import (
    CareerTwinService,
    get_career_twin_service,
)

router = APIRouter(prefix="/career-twin", tags=["career-twin"])


@router.get("/persona", response_model=TwinPersonaOut, summary="My twin persona")
async def get_persona(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CareerTwinService = Depends(get_career_twin_service),
) -> TwinPersonaOut:
    return await service.get_persona(user.uid)


@router.put("/persona", response_model=TwinPersonaOut, summary="Configure persona")
async def upsert_persona(
    payload: TwinPersonaUpsert,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CareerTwinService = Depends(get_career_twin_service),
) -> TwinPersonaOut:
    return await service.upsert_persona(user.uid, payload)


@router.get("/today", response_model=DailyCheckinOut, summary="Today's check-in")
async def today(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CareerTwinService = Depends(get_career_twin_service),
) -> DailyCheckinOut:
    return await service.today(user.uid)


@router.post(
    "/{checkin_id}/reply", response_model=DailyCheckinOut, summary="Reply to a check-in"
)
async def reply(
    checkin_id: str,
    payload: CheckinReply,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CareerTwinService = Depends(get_career_twin_service),
) -> DailyCheckinOut:
    return await service.reply(user.uid, checkin_id, payload.reply, payload.mood)


@router.get("/history", response_model=list[DailyCheckinOut], summary="Check-in journal")
async def history(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CareerTwinService = Depends(get_career_twin_service),
) -> list[DailyCheckinOut]:
    return await service.history(user.uid)
