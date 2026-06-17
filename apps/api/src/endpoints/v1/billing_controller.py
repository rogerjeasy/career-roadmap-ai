"""Billing — Stripe-backed Pro subscription.

Routes:
  GET  /api/v1/billing/subscription  — current plan/status (auth)
  POST /api/v1/billing/checkout      — start a Checkout Session, returns a URL (auth)
  POST /api/v1/billing/portal        — open the Billing Portal, returns a URL (auth)
  POST /api/v1/billing/webhook       — Stripe webhook (no auth; signature-verified)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.domains.billing.schemas import (
    CheckoutSessionOut,
    PortalSessionOut,
    SubscriptionOut,
)
from src.domains.billing.service import BillingService, get_billing_service
from src.domains.billing.stripe_client import StripeSignatureError

router = APIRouter(prefix="/billing", tags=["billing"])
logger = get_logger(__name__)


@router.get(
    "/subscription",
    response_model=SubscriptionOut,
    summary="Get the current user's subscription",
)
async def get_subscription(
    user: AuthenticatedUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    return await service.get_subscription(user.uid)


@router.post(
    "/checkout",
    response_model=CheckoutSessionOut,
    summary="Start a Stripe Checkout session for the Pro plan",
)
async def create_checkout(
    user: AuthenticatedUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> CheckoutSessionOut:
    return await service.start_checkout(user.uid, user.email)


@router.post(
    "/portal",
    response_model=PortalSessionOut,
    summary="Open the Stripe Billing Portal",
)
async def create_portal(
    user: AuthenticatedUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> PortalSessionOut:
    return await service.open_portal(user.uid)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook receiver (signature-verified, no auth)",
    include_in_schema=False,
)
async def stripe_webhook(
    request: Request,
    service: BillingService = Depends(get_billing_service),
) -> dict[str, bool]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = service.parse_webhook(payload, sig)
    except StripeSignatureError as exc:
        logger.warning("billing.webhook_rejected", reason=str(exc))
        # 400 tells Stripe the event was not accepted (it will retry).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature."
        ) from exc

    await service.handle_event(event)
    return {"received": True}
