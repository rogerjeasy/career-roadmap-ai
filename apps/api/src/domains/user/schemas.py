"""User domain — Pydantic request and response schemas.

Fields use snake_case (Python convention).
CaseConversionMiddleware translates to/from camelCase at the HTTP boundary.
"""
from datetime import datetime

from pydantic import ConfigDict, EmailStr, Field

from src.core.schema import BaseSchema


# ── Request schemas ───────────────────────────────────────────────────────────

class RegisterEmailRequest(BaseSchema):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")
    display_name: str | None = Field(default=None, max_length=200)


class LoginEmailRequest(BaseSchema):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseSchema):
    refresh_token: str


# ── Response schemas ──────────────────────────────────────────────────────────

class UserProfile(BaseSchema):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,   # allows model_validate(User dataclass)
    )

    id: str
    firebase_uid: str
    email: str
    display_name: str | None
    photo_url: str | None
    provider: str
    email_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseSchema):
    """Returned on successful email register or login — includes tokens."""

    user: UserProfile
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class TokenRefreshResponse(BaseSchema):
    """Returned when an ID token is refreshed using a refresh token."""

    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
