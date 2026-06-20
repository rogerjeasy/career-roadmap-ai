"""Newsletter — read and update the user's career-digest preferences.

Routes:
  GET /api/v1/newsletter   — current preferences (defaults if never set)
  PUT /api/v1/newsletter   — upsert preferences
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.newsletter.schemas import (
    NewsletterDigest,
    NewsletterPrefsOut,
    NewsletterPrefsUpdate,
)
from src.domains.newsletter.service import NewsletterService, get_newsletter_service
from src.domains.push.service import PushService, get_push_service
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/newsletter", tags=["newsletter"])


@router.get("", response_model=NewsletterPrefsOut, summary="Get newsletter preferences")
async def get_newsletter_prefs(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NewsletterService = Depends(get_newsletter_service),
) -> NewsletterPrefsOut:
    return await service.get(user.uid)


@router.put(
    "", response_model=NewsletterPrefsOut, summary="Update newsletter preferences"
)
async def update_newsletter_prefs(
    body: NewsletterPrefsUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NewsletterService = Depends(get_newsletter_service),
) -> NewsletterPrefsOut:
    return await service.update(user.uid, body)


@router.get(
    "/digest",
    response_model=NewsletterDigest,
    summary="Get the latest generated digest",
)
async def get_digest(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NewsletterService = Depends(get_newsletter_service),
) -> NewsletterDigest:
    return await service.get_digest(user.uid)


@router.post(
    "/digest/generate",
    response_model=NewsletterDigest,
    summary="Generate this week's digest",
)
async def generate_digest(
    user: AuthenticatedUser = Depends(get_current_user),
    service: NewsletterService = Depends(get_newsletter_service),
) -> NewsletterDigest:
    return await service.generate_digest(user.uid)


@router.post(
    "/digest/deliver",
    response_model=NewsletterDigest,
    summary="Deliver the latest digest to my webhooks + devices",
)
async def deliver_digest(
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: NewsletterService = Depends(get_newsletter_service),
    webhooks: WebhookService = Depends(get_webhook_service),
    push: PushService = Depends(get_push_service),
) -> NewsletterDigest:
    """Push the latest digest out via the user's registered delivery channels.

    Reuses the webhooks fabric (so a Slack/Zapier/email-relay endpoint can receive
    it) and sends a push notification. Delivery runs after the response returns.
    """
    digest = await service.get_digest(user.uid)
    payload = {
        "period_label": digest.period_label,
        "summary": digest.summary,
        "action_item": digest.action_item,
        "articles": [{"title": a.title, "url": a.url} for a in digest.articles],
    }
    background.add_task(webhooks.dispatch, user.uid, "newsletter.digest", payload)
    background.add_task(
        push.send_to_user,
        user.uid,
        title="Your weekly digest is ready",
        body=digest.summary[:120] or "Open to read this week's digest.",
        url="/newsletter",
    )
    return digest
