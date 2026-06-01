"""Notifications domain — public surface."""
from src.domains.notifications.schemas import (
    NotificationCreate,
    NotificationListOut,
    NotificationOut,
)
from src.domains.notifications.service import (
    NotificationService,
    get_notification_service,
)

__all__ = [
    "NotificationCreate",
    "NotificationListOut",
    "NotificationOut",
    "NotificationService",
    "get_notification_service",
]
