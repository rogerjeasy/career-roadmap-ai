"""Web Push — service layer.

Manages subscriptions and sends notifications via VAPID. The actual send uses
``pywebpush`` when available; the import is optional and guarded so the platform
runs fine without it. ``send_to_user`` is the reusable nudge entry point for
other domains.
"""
from __future__ import annotations

import json

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.config import settings
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.push.firestore_repository import FirestorePushRepository, device_id
from src.domains.push.schemas import (
    PushConfig,
    PushSendResult,
    PushSubscriptionIn,
)

logger = get_logger(__name__)


def _push_enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


class PushService:
    def __init__(self, repo: FirestorePushRepository) -> None:
        self._repo = repo

    def config(self) -> PushConfig:
        return PushConfig(enabled=_push_enabled(), public_key=settings.vapid_public_key)

    async def subscribe(self, user_id: str, sub: PushSubscriptionIn) -> None:
        await self._repo.create(
            user_id,
            {
                "endpoint": sub.endpoint,
                "keys": sub.keys.model_dump(),
                "expiration_time": sub.expiration_time,
            },
            doc_id=device_id(sub.endpoint),
        )
        logger.info("push.subscribed", user_id=user_id)

    async def unsubscribe(self, user_id: str, endpoint: str) -> None:
        await self._repo.hard_delete(device_id(endpoint), user_id)
        logger.info("push.unsubscribed", user_id=user_id)

    async def send_test(self, user_id: str) -> PushSendResult:
        return await self.send_to_user(
            user_id,
            title="Career Roadmap AI",
            body="Push notifications are working. We'll nudge you here.",
            url="/dashboard",
        )

    async def send_to_user(
        self, user_id: str, *, title: str, body: str, url: str = "/dashboard"
    ) -> PushSendResult:
        if not _push_enabled():
            return PushSendResult(
                sent=0, failed=0, enabled=False, detail="Push is not configured on the server."
            )
        try:
            from pywebpush import WebPushException, webpush  # noqa: PLC0415
        except ImportError:
            logger.warning("push.pywebpush_missing")
            return PushSendResult(
                sent=0, failed=0, enabled=False, detail="pywebpush is not installed."
            )

        subs = await self._repo.list_for_user(user_id, limit=50)
        payload = json.dumps({"title": title, "body": body, "url": url})
        vapid_private = settings.vapid_private_key.get_secret_value()  # type: ignore[union-attr]
        sent = failed = 0
        for s in subs:
            try:
                webpush(
                    subscription_info={"endpoint": s.get("endpoint"), "keys": s.get("keys", {})},
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": settings.vapid_subject},
                )
                sent += 1
            except WebPushException as exc:
                failed += 1
                # 404/410 → the subscription is dead; prune it.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    try:
                        await self._repo.hard_delete(s["id"], user_id)
                    except Exception:  # noqa: BLE001
                        pass
                logger.warning("push.send_failed", user_id=user_id, status=status)
        return PushSendResult(sent=sent, failed=failed, enabled=True)


async def get_push_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> PushService:
    return PushService(FirestorePushRepository(db))
