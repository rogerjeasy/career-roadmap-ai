"""Billing domain — service layer (Stripe-backed Pro subscription).

Subscription state is the source-of-truth-by-mirror: Stripe owns it, and webhook
events keep a Firestore copy (``billing_customers/{uid}``) that the app reads.
Reads never call Stripe; only checkout/portal creation does.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends

from src.config import Settings, get_settings
from src.core.exceptions import (
    ExternalServiceError,
    NotFoundError,
    ServiceUnavailableError,
)
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.http import get_http_client
from src.domains.billing.firestore_repository import FirestoreBillingRepository
from src.domains.billing.schemas import (
    CheckoutSessionOut,
    PortalSessionOut,
    SubscriptionOut,
)
from src.domains.billing.stripe_client import (
    StripeClient,
    StripeError,
    verify_webhook,
)

logger = get_logger(__name__)


def _epoch_to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


class BillingService:
    def __init__(
        self,
        settings: Settings,
        repo: FirestoreBillingRepository,
        http: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._http = http

    # ── Config helpers ────────────────────────────────────────────────────────

    @property
    def _secret_key(self) -> str | None:
        sk = self._settings.stripe_secret_key
        return sk.get_secret_value() if sk else None

    @property
    def _webhook_secret(self) -> str | None:
        ws = self._settings.stripe_webhook_secret
        return ws.get_secret_value() if ws else None

    @property
    def is_configured(self) -> bool:
        return bool(self._secret_key and self._settings.stripe_price_pro)

    def _stripe(self) -> StripeClient:
        if not self._secret_key:
            raise ServiceUnavailableError("Billing is not configured.")
        return StripeClient(self._secret_key, self._http)

    def _plan_for_price(self, price_id: str | None) -> str:
        if price_id and price_id == self._settings.stripe_price_pro:
            return "pro"
        return "pro" if price_id else "free"

    # ── Reads ───────────────────────────────────────────────────────────────────

    async def get_subscription(self, user_id: str) -> SubscriptionOut:
        doc = await self._repo.get_for_user(user_id)
        return SubscriptionOut.from_doc(doc) if doc else SubscriptionOut.free()

    # ── Checkout / portal ─────────────────────────────────────────────────────

    async def _ensure_customer(self, user_id: str, email: str | None) -> str:
        doc = await self._repo.get_for_user(user_id)
        if doc and doc.get("stripe_customer_id"):
            return str(doc["stripe_customer_id"])
        try:
            customer_id = await self._stripe().create_customer(email=email, uid=user_id)
        except StripeError as exc:
            logger.error("billing.customer_create_failed", user_id=user_id, error=str(exc))
            raise ExternalServiceError("Couldn't reach billing provider.") from exc
        await self._repo.upsert_for_user(user_id, {"stripe_customer_id": customer_id})
        return customer_id

    async def start_checkout(self, user_id: str, email: str | None) -> CheckoutSessionOut:
        if not self.is_configured:
            raise ServiceUnavailableError("Billing is not configured.")
        customer = await self._ensure_customer(user_id, email)
        try:
            url = await self._stripe().create_checkout_session(
                customer=customer,
                price=str(self._settings.stripe_price_pro),
                success_url=self._settings.billing_success_url,
                cancel_url=self._settings.billing_cancel_url,
                uid=user_id,
                trial_days=self._settings.stripe_trial_days,
            )
        except StripeError as exc:
            logger.error("billing.checkout_failed", user_id=user_id, error=str(exc))
            raise ExternalServiceError("Couldn't start checkout. Please try again.") from exc
        logger.info("billing.checkout_started", user_id=user_id)
        return CheckoutSessionOut(url=url)

    async def open_portal(self, user_id: str) -> PortalSessionOut:
        if not self.is_configured:
            raise ServiceUnavailableError("Billing is not configured.")
        doc = await self._repo.get_for_user(user_id)
        customer = doc.get("stripe_customer_id") if doc else None
        if not customer:
            raise NotFoundError("No billing account yet — start a subscription first.")
        return_url = f"{self._settings.frontend_base_url.rstrip('/')}/settings/billing"
        try:
            url = await self._stripe().create_portal_session(
                customer=str(customer), return_url=return_url
            )
        except StripeError as exc:
            logger.error("billing.portal_failed", user_id=user_id, error=str(exc))
            raise ExternalServiceError("Couldn't open the billing portal.") from exc
        return PortalSessionOut(url=url)

    # ── Webhook handling ──────────────────────────────────────────────────────

    def parse_webhook(self, payload: bytes, sig_header: str | None) -> dict[str, Any]:
        """Verify the signature and return the event (raises on bad signature)."""
        secret = self._webhook_secret
        if not secret:
            raise ServiceUnavailableError("Billing webhook is not configured.")
        return verify_webhook(payload, sig_header, secret)

    async def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")
        obj = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            await self._on_checkout_completed(obj)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            await self._on_subscription_changed(obj)
        elif event_type == "customer.subscription.deleted":
            await self._on_subscription_deleted(obj)
        else:
            logger.info("billing.webhook_ignored", event_type=event_type)
            return
        logger.info("billing.webhook_processed", event_type=event_type)

    async def _on_checkout_completed(self, session: dict[str, Any]) -> None:
        uid = session.get("client_reference_id")
        customer = session.get("customer")
        if not uid:
            return
        await self._repo.upsert_for_user(
            uid,
            {
                "stripe_customer_id": customer,
                "subscription_id": session.get("subscription"),
                "plan": "pro",
                "status": "active",
            },
        )

    def _uid_from_subscription(self, sub: dict[str, Any]) -> str | None:
        meta = sub.get("metadata") or {}
        return meta.get("uid")

    async def _resolve_uid(self, sub: dict[str, Any]) -> str | None:
        uid = self._uid_from_subscription(sub)
        if uid:
            return uid
        customer = sub.get("customer")
        if not customer:
            return None
        doc = await self._repo.find_by_customer_id(str(customer))
        return doc["id"] if doc else None

    async def _on_subscription_changed(self, sub: dict[str, Any]) -> None:
        uid = await self._resolve_uid(sub)
        if not uid:
            logger.warning("billing.subscription_uid_unresolved", customer=sub.get("customer"))
            return
        items = (sub.get("items") or {}).get("data") or []
        price_id = items[0].get("price", {}).get("id") if items else None
        await self._repo.upsert_for_user(
            uid,
            {
                "stripe_customer_id": sub.get("customer"),
                "subscription_id": sub.get("id"),
                "plan": self._plan_for_price(price_id),
                "status": sub.get("status", "active"),
                "current_period_end": _epoch_to_dt(sub.get("current_period_end")),
                "cancel_at_period_end": bool(sub.get("cancel_at_period_end", False)),
                "trial_end": _epoch_to_dt(sub.get("trial_end")),
            },
        )

    async def _on_subscription_deleted(self, sub: dict[str, Any]) -> None:
        uid = await self._resolve_uid(sub)
        if not uid:
            return
        await self._repo.upsert_for_user(
            uid,
            {
                "subscription_id": None,
                "plan": "free",
                "status": "canceled",
                "cancel_at_period_end": False,
            },
        )


async def get_billing_service(
    db=Depends(get_firestore_client),
    http: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> BillingService:
    return BillingService(settings, FirestoreBillingRepository(db), http)
