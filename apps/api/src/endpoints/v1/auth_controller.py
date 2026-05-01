"""Auth controller — registration, login, token refresh, and logout endpoints."""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.user.schemas import (
    AuthResponse,
    LoginEmailRequest,
    RefreshTokenRequest,
    RegisterEmailRequest,
    TokenRefreshResponse,
    UserProfile,
)
from src.domains.user.service import UserService, get_user_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register with email and password",
)
async def register_email(
    body: RegisterEmailRequest,
    service: UserService = Depends(get_user_service),
) -> AuthResponse:
    """
    Create a new account using email and password.

    - Creates the user in Firebase Auth and in the application database.
    - Returns an ID token and refresh token ready to use immediately.
    - The account email is unverified until the user completes email verification.
    """
    user, id_token, refresh_token, expires_in = await service.register_with_email(
        email=str(body.email),
        password=body.password,
        display_name=body.display_name,
    )
    return AuthResponse(
        user=UserProfile.model_validate(user),
        id_token=id_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login_email(
    body: LoginEmailRequest,
    service: UserService = Depends(get_user_service),
) -> AuthResponse:
    """
    Sign in with email and password.

    - Authenticates against Firebase Auth.
    - Syncs the user record to the application database on first login.
    - Returns an ID token (short-lived) and a refresh token (long-lived).
    """
    user, id_token, refresh_token, expires_in = await service.login_with_email(
        email=str(body.email),
        password=body.password,
    )
    return AuthResponse(
        user=UserProfile.model_validate(user),
        id_token=id_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post(
    "/google",
    response_model=UserProfile,
    summary="Sync after Google sign-in",
)
async def login_google(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserProfile:
    """
    Sync a Google-authenticated user with the application database.

    Call this endpoint after the client completes Google sign-in via the
    Firebase JS SDK and obtains a Firebase ID token. Send that token in the
    `Authorization: Bearer <id_token>` header.

    - Verifies the Firebase ID token server-side.
    - Creates or updates the user record in the application database.
    - The client already holds the ID token and refresh token from Firebase.
    """
    user = await service.login_with_google(auth_user)
    return UserProfile.model_validate(user)


@router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    summary="Refresh an access token",
)
async def refresh_token(
    body: RefreshTokenRequest,
    service: UserService = Depends(get_user_service),
) -> TokenRefreshResponse:
    """
    Exchange a Firebase refresh token for a new ID token.

    Firebase ID tokens expire after 1 hour. Use this endpoint to obtain a
    fresh ID token without requiring the user to log in again.
    """
    id_token, new_refresh_token, expires_in = await service.refresh_access_token(body.refresh_token)
    return TokenRefreshResponse(
        id_token=id_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke tokens",
)
async def logout(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> None:
    """
    Revoke all active refresh tokens for the authenticated user.

    After this call, any previously issued refresh tokens become invalid.
    The client should discard the stored ID token and refresh token.
    """
    await service.logout(auth_user.uid)
