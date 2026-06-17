"""Billing domain — Pydantic schemas for the Stripe-backed Pro subscription."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

BillingPlan = Literal["free", "pro", "teams"]
SubscriptionStatus = Literal[
    "none",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "incomplete",
    "unpaid",
]

_VALID_STATUS = {
    "trialing",
    "active",
    "past_due",
    "canceled",
    "incomplete",
    "unpaid",
}


class SubscriptionOut(BaseModel):
    plan: BillingPlan = "free"
    status: SubscriptionStatus = "none"
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    trial_end: datetime | None = None
    # True when there's a Stripe customer on file (so the UI can offer "manage").
    has_billing_account: bool = False

    @classmethod
    def free(cls) -> "SubscriptionOut":
        return cls()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "SubscriptionOut":
        plan = doc.get("plan", "free")
        status = doc.get("status", "none")
        return cls(
            plan=plan if plan in ("free", "pro", "teams") else "free",
            status=status if status in _VALID_STATUS else "none",
            current_period_end=doc.get("current_period_end"),
            cancel_at_period_end=bool(doc.get("cancel_at_period_end", False)),
            trial_end=doc.get("trial_end"),
            has_billing_account=bool(doc.get("stripe_customer_id")),
        )


class CheckoutSessionOut(BaseModel):
    url: str


class PortalSessionOut(BaseModel):
    url: str
