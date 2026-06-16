"""User controller — authenticated user profile endpoints."""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.user.schemas import UserProfile, UserUpdate
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


@router.patch(
    "/me",
    response_model=UserProfile,
    summary="Update current user profile",
)
async def update_me(
    body: UserUpdate,
    auth_user: AuthenticatedUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserProfile:
    """
    Partially update the authenticated user's profile.

    Only the fields included in the request body are changed; omitted fields are
    left untouched. ``displayName`` is mirrored into Firebase Auth, and
    ``notificationPreferences`` is persisted to the user's profile document.
    """
    updates = body.model_dump(exclude_unset=True)
    user = await service.update_profile(auth_user, updates)
    return UserProfile.model_validate(user)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current user account",
)
async def delete_me(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> None:
    """
    Permanently delete the authenticated user's account.

    Removes the Firestore profile document and the Firebase Auth user, and
    revokes outstanding refresh tokens. This action is irreversible.
    """
    await service.delete_account(auth_user.uid)
