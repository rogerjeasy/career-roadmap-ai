"""Newsletter — read and update the user's career-digest preferences.

Routes:
  GET /api/v1/newsletter   — current preferences (defaults if never set)
  PUT /api/v1/newsletter   — upsert preferences
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.newsletter.schemas import (
    NewsletterDigest,
    NewsletterPrefsOut,
    NewsletterPrefsUpdate,
)
from src.domains.newsletter.service import NewsletterService, get_newsletter_service

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
