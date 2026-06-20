"""Webhooks domain — service layer.

Manages webhook registrations and delivers signed events. ``dispatch`` is the
reuse entry point for event sources: it finds the user's active webhooks
subscribed to the event and POSTs a signed payload to each, best-effort, stamping
the last delivery status. Deliveries never raise into the calling request.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets as secretslib
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.http import get_http_client
from src.domains.webhooks.firestore_repository import FirestoreWebhookRepository
from src.domains.webhooks.schemas import (
    WebhookCreate,
    WebhookCreated,
    WebhookOut,
    WebhookPingResult,
)

logger = get_logger(__name__)


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _subscribed(events: list[str], event: str) -> bool:
    return "*" in events or event in events


class WebhookService:
    def __init__(self, repo: FirestoreWebhookRepository, http: httpx.AsyncClient) -> None:
        self._repo = repo
        self._http = http

    async def list(self, user_id: str) -> list[WebhookOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [WebhookOut.from_doc(d) for d in docs]

    async def create(self, user_id: str, payload: WebhookCreate) -> WebhookCreated:
        secret = "whsec_" + secretslib.token_urlsafe(24)
        doc = await self._repo.create(
            user_id,
            {
                "url": str(payload.url),
                "events": payload.events or ["*"],
                "active": True,
                "secret": secret,
                "last_status": None,
                "last_delivery_at": None,
            },
        )
        logger.info("webhook.created", user_id=user_id, webhook_id=doc["id"])
        out = WebhookOut.from_doc(doc)
        return WebhookCreated(**out.model_dump(), secret=secret)

    async def delete(self, user_id: str, webhook_id: str) -> None:
        removed = await self._repo.hard_delete(webhook_id, user_id)
        if not removed:
            raise NotFoundError("Webhook not found.")

    async def ping(self, user_id: str, webhook_id: str) -> WebhookPingResult:
        doc = await self._repo.get(webhook_id, user_id)
        if doc is None:
            raise NotFoundError("Webhook not found.")
        status, detail = await self._deliver(
            user_id, doc, event="ping", data={"message": "Test event from Career Roadmap AI"}
        )
        return WebhookPingResult(delivered=status is not None and status < 400, status=status, detail=detail)

    async def dispatch(self, user_id: str, event: str, data: dict[str, Any]) -> None:
        """Deliver an event to all of the user's matching active webhooks."""
        docs = await self._repo.list_for_user(user_id, limit=100)
        for doc in docs:
            if not doc.get("active", True):
                continue
            if not _subscribed(doc.get("events", []), event):
                continue
            await self._deliver(user_id, doc, event=event, data=data)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _deliver(
        self, user_id: str, doc: dict, *, event: str, data: dict[str, Any]
    ) -> tuple[int | None, str]:
        body = json.dumps(
            {"event": event, "created_at": datetime.now(timezone.utc).isoformat(), "data": data},
            separators=(",", ":"),
        )
        signature = _sign(str(doc.get("secret", "")), body)
        status: int | None = None
        detail = ""
        try:
            resp = await self._http.post(
                str(doc.get("url")),
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-CRA-Event": event,
                    "X-CRA-Signature": f"sha256={signature}",
                    "User-Agent": "career-roadmap-ai-webhooks",
                },
                timeout=8.0,
            )
            status = resp.status_code
        except httpx.HTTPError as exc:
            detail = f"delivery failed: {exc.__class__.__name__}"
            logger.warning("webhook.delivery_failed", user_id=user_id, error=str(exc))
        try:
            await self._repo.update(
                doc["id"], user_id, {"last_status": status, "last_delivery_at": datetime.now(timezone.utc)}
            )
        except Exception:  # noqa: BLE001
            pass
        return status, detail


async def get_webhook_service(
    db: AsyncClient = Depends(get_firestore_client),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> WebhookService:
    return WebhookService(FirestoreWebhookRepository(db), http)
