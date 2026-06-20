"""Web Push (§17) — subscription management + test send.

Routes:
  GET    /api/v1/push/config        — VAPID public key + whether push is enabled
  POST   /api/v1/push/subscribe     — register this device's subscription
  POST   /api/v1/push/unsubscribe   — remove a device subscription
  POST   /api/v1/push/test          — send a test notification to my devices
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.push.schemas import (
    PushConfig,
    PushSendResult,
    PushSubscriptionIn,
    PushUnsubscribe,
)
from src.domains.push.service import PushService, get_push_service

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/config", response_model=PushConfig, summary="Push config (public key)")
async def get_config(
    service: PushService = Depends(get_push_service),
) -> PushConfig:
    return service.config()


@router.post(
    "/subscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Register a push subscription",
)
async def subscribe(
    payload: PushSubscriptionIn,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PushService = Depends(get_push_service),
) -> None:
    await service.subscribe(user.uid, payload)


@router.post(
    "/unsubscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a push subscription",
)
async def unsubscribe(
    payload: PushUnsubscribe,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PushService = Depends(get_push_service),
) -> None:
    await service.unsubscribe(user.uid, payload.endpoint)


@router.post("/test", response_model=PushSendResult, summary="Send a test notification")
async def send_test(
    user: AuthenticatedUser = Depends(get_current_user),
    service: PushService = Depends(get_push_service),
) -> PushSendResult:
    return await service.send_test(user.uid)
