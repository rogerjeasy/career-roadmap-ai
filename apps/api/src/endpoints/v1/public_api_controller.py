"""Public API (§21) — API-key-authenticated read access to your own data.

Authenticated with an ``X-API-Key`` header (not Firebase). Demonstrates the
public-API pillar of the platform vision: a developer can read their profile and
roadmap summary programmatically.

Routes:
  GET    /api/v1/public/me   — the key owner's profile + roadmap summary
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.domains.api_keys.schemas import PublicProfile, PublicRoadmap
from src.domains.api_keys.service import ApiKeyService, get_api_key_service

router = APIRouter(prefix="/public", tags=["public-api"])


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    service: ApiKeyService = Depends(get_api_key_service),
) -> str:
    """Resolve a valid X-API-Key header to its owning user id, or 401."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide your key in the X-API-Key header.",
        )
    user_id = await service.authenticate(x_api_key)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )
    return user_id


@router.get("/me", response_model=PublicProfile, summary="Your profile (API key auth)")
async def public_me(
    user_id: str = Depends(require_api_key),
    service: ApiKeyService = Depends(get_api_key_service),
) -> PublicProfile:
    return await service.public_profile(user_id)


@router.get("/roadmap", response_model=PublicRoadmap, summary="Your roadmap (API key auth)")
async def public_roadmap(
    user_id: str = Depends(require_api_key),
    service: ApiKeyService = Depends(get_api_key_service),
) -> PublicRoadmap:
    return await service.public_roadmap(user_id)
