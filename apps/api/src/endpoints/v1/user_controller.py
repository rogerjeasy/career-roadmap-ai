"""User controller — authenticated user profile endpoints."""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.user.schemas import UserProfile
from src.domains.user.service import UserService, get_user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user profile",
)
async def get_me(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserProfile:
    """
    Return the full profile of the currently authenticated user.

    Requires a valid Firebase ID token in the `Authorization: Bearer` header.
    If the user does not yet have a database record (e.g. registered externally),
    one is created automatically on first call.
    """
    user = await service.get_profile(auth_user)
    return UserProfile.model_validate(user)
