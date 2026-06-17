"""Minimal Stripe client over the shared httpx client + webhook verification.

We talk to Stripe's REST API directly (form-encoded, Bearer auth) rather than
pulling in the ``stripe`` SDK — it keeps the dependency surface small and reuses
the app's shared ``httpx.AsyncClient``. Only the handful of calls the Pro
subscription needs are implemented.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

_STRIPE_API = "https://api.stripe.com"
_TIMEOUT = httpx.Timeout(20.0)
# Reject webhook timestamps older than this (replay protection), matching
# Stripe's own default tolerance.
_WEBHOOK_TOLERANCE_SECONDS = 300


class StripeError(Exception):
    """Any non-2xx Stripe response or transport failure."""


class StripeSignatureError(Exception):
    """The webhook signature header is missing, malformed, or invalid."""


class StripeClient:
    def __init__(self, secret_key: str, http: httpx.AsyncClient) -> None:
        self._key = secret_key
        self._http = http

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._http.post(
                f"{_STRIPE_API}{path}",
                data=data,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise StripeError(f"Stripe request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise StripeError(
                f"Stripe {path} returned {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    async def create_customer(self, *, email: str | None, uid: str) -> str:
        data: dict[str, Any] = {"metadata[uid]": uid}
        if email:
            data["email"] = email
        result = await self._post("/v1/customers", data)
        return str(result["id"])

    async def create_checkout_session(
        self,
        *,
        customer: str,
        price: str,
        success_url: str,
        cancel_url: str,
        uid: str,
        trial_days: int,
    ) -> str:
        data: dict[str, Any] = {
            "mode": "subscription",
            "customer": customer,
            "line_items[0][price]": price,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": uid,
            "subscription_data[metadata][uid]": uid,
        }
        if trial_days > 0:
            data["subscription_data[trial_period_days]"] = str(trial_days)
        result = await self._post("/v1/checkout/sessions", data)
        return str(result["url"])

    async def create_portal_session(self, *, customer: str, return_url: str) -> str:
        result = await self._post(
            "/v1/billing_portal/sessions",
            {"customer": customer, "return_url": return_url},
        )
        return str(result["url"])


def verify_webhook(payload: bytes, sig_header: str | None, secret: str) -> dict[str, Any]:
    """Verify a Stripe webhook signature and return the parsed event.

    Implements Stripe's scheme: ``signed_payload = "{t}.{body}"`` signed with
    HMAC-SHA256 using the endpoint secret; the result must match a ``v1``
    signature in the ``Stripe-Signature`` header, within the timestamp tolerance.
    """
    if not sig_header:
        raise StripeSignatureError("Missing Stripe-Signature header.")

    parts = dict(
        item.split("=", 1) for item in sig_header.split(",") if "=" in item
    )
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        raise StripeSignatureError("Malformed Stripe-Signature header.")

    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        raise StripeSignatureError("Invalid signature timestamp.") from exc

    if abs(time.time() - ts_int) > _WEBHOOK_TOLERANCE_SECONDS:
        raise StripeSignatureError("Signature timestamp outside tolerance.")

    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise StripeSignatureError("Signature mismatch.")

    try:
        return json.loads(payload)
    except ValueError as exc:
        raise StripeSignatureError("Webhook body is not valid JSON.") from exc
