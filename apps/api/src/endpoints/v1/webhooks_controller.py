"""Webhooks (§21) — register signed event endpoints.

Routes:
  GET    /api/v1/webhooks            — my webhooks
  POST   /api/v1/webhooks            — register one (signing secret returned ONCE)
  POST   /api/v1/webhooks/{id}/ping  — send a test event
  DELETE /api/v1/webhooks/{id}       — remove a webhook
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.webhooks.schemas import (
    WebhookCreate,
    WebhookCreated,
    WebhookOut,
    WebhookPingResult,
)
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("", response_model=list[WebhookOut], summary="My webhooks")
async def list_webhooks(
    user: AuthenticatedUser = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookOut]:
    return await service.list(user.uid)


@router.post(
    "",
    response_model=WebhookCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Register a webhook",
)
async def create_webhook(
    payload: WebhookCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookCreated:
    return await service.create(user.uid, payload)


@router.post(
    "/{webhook_id}/ping", response_model=WebhookPingResult, summary="Send a test event"
)
async def ping_webhook(
    webhook_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookPingResult:
    return await service.ping(user.uid, webhook_id)


@router.delete(
    "/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a webhook"
)
async def delete_webhook(
    webhook_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> None:
    await service.delete(user.uid, webhook_id)
