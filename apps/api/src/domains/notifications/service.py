"""Notifications domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.notifications.firestore_repository import FirestoreNotificationRepository
from src.domains.notifications.schemas import NotificationCreate, NotificationOut

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, repo: FirestoreNotificationRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str, limit: int = 30) -> list[NotificationOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [NotificationOut.from_doc(d) for d in docs]

    async def unread_count(self, user_id: str) -> int:
        return await self._repo.count_unread(user_id)

    async def create(self, user_id: str, payload: NotificationCreate) -> NotificationOut:
        doc = await self._repo.create(
            user_id,
            {
                "title": payload.title,
                "body": payload.body,
                "tone": payload.tone,
                "link": payload.link,
                "read": False,
            },
        )
        return NotificationOut.from_doc(doc)

    async def mark_read(self, user_id: str, notification_id: str) -> NotificationOut:
        doc = await self._repo.update(notification_id, user_id, {"read": True})
        if doc is None:
            raise NotFoundError(f"Notification '{notification_id}' not found")
        return NotificationOut.from_doc(doc)

    async def mark_all_read(self, user_id: str) -> int:
        return await self._repo.mark_all_read(user_id)

    async def delete(self, user_id: str, notification_id: str) -> None:
        deleted = await self._repo.hard_delete(notification_id, user_id)
        if not deleted:
            raise NotFoundError(f"Notification '{notification_id}' not found")


async def get_notification_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> NotificationService:
    return NotificationService(FirestoreNotificationRepository(db))
