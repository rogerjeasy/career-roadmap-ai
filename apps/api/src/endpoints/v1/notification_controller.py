"""Notifications — list, mark read, and delete the user's notifications.

Routes:
  GET    /api/v1/notifications                  — list (newest-first) + unread count
  POST   /api/v1/notifications                  — create a notification
  POST   /api/v1/notifications/read-all         — mark all as read
  PATCH  /api/v1/notifications/{id}/read        — mark one as read
  DELETE /api/v1/notifications/{id}             — delete one
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.domains.notifications.schemas import (
    NotificationCreate,
    NotificationListOut,
    NotificationOut,
)
from src.domains.notifications.service import (
    NotificationService,
    get_notification_service,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = get_logger(__name__)


@router.get("", response_model=NotificationListOut, summary="List notifications")
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListOut:
    items = await service.list(user.uid, limit=limit)
    unread = await service.unread_count(user.uid)
    return NotificationListOut(items=items, unread_count=unread)


@router.post(
    "",
    response_model=NotificationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a notification",
)
async def create_notification(
    body: NotificationCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationOut:
    return await service.create(user.uid, body)


@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_read(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> dict[str, int]:
    updated = await service.mark_all_read(user.uid)
    return {"updated": updated}


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark a notification as read",
)
async def mark_read(
    notification_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationOut:
    return await service.mark_read(user.uid, notification_id)


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a notification",
)
async def delete_notification(
    notification_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.delete(user.uid, notification_id)
