"""Unit tests for Firebase auth helpers (``src.core.auth``).

``firebase_admin.auth.verify_id_token`` is patched everywhere — no network and
no Firebase project are required. The tests cover the token→user mapping, the
role-claim hardening, and the admin/superadmin gates.
"""
from unittest.mock import patch

import pytest
from firebase_admin import auth as firebase_auth

from src.core.auth import (
    ROLE_ADMIN,
    ROLE_SUPERADMIN,
    ROLE_USER,
    AuthenticatedUser,
    get_current_user,
    require_admin,
    require_superadmin,
)
from src.core.exceptions import AuthenticationError, AuthorizationError

pytestmark = pytest.mark.unit


class _Creds:
    def __init__(self, token: str) -> None:
        self.credentials = token


# ── AuthenticatedUser role properties ───────────────────────────────────────────


def test_default_role_is_user_and_not_admin() -> None:
    u = AuthenticatedUser("u1", "e@x.com", True, "N", "password")
    assert u.role == ROLE_USER
    assert u.is_admin is False
    assert u.is_superadmin is False


def test_admin_is_admin_but_not_superadmin() -> None:
    u = AuthenticatedUser("u1", "e@x.com", True, "N", "password", role=ROLE_ADMIN)
    assert u.is_admin is True
    assert u.is_superadmin is False


def test_superadmin_is_both() -> None:
    u = AuthenticatedUser("u1", "e@x.com", True, "N", "password", role=ROLE_SUPERADMIN)
    assert u.is_admin is True
    assert u.is_superadmin is True


# ── get_current_user ────────────────────────────────────────────────────────────


async def test_missing_credentials_raises_authentication_error() -> None:
    with pytest.raises(AuthenticationError, match="Missing authorization token"):
        await get_current_user(http_creds=None)


async def test_valid_token_maps_to_authenticated_user() -> None:
    decoded = {
        "uid": "abc",
        "email": "a@b.com",
        "email_verified": True,
        "name": "Ada",
        "firebase": {"sign_in_provider": "google.com"},
        "role": "admin",
    }
    with patch.object(firebase_auth, "verify_id_token", return_value=decoded):
        u = await get_current_user(http_creds=_Creds("tok"))
    assert u.uid == "abc"
    assert u.email == "a@b.com"
    assert u.sign_in_provider == "google.com"
    assert u.role == "admin"


async def test_unknown_role_claim_is_downgraded_to_user() -> None:
    decoded = {"uid": "abc", "role": "root"}  # not in the allow-list
    with patch.object(firebase_auth, "verify_id_token", return_value=decoded):
        u = await get_current_user(http_creds=_Creds("tok"))
    assert u.role == ROLE_USER


async def test_expired_token_raises_authentication_error() -> None:
    with patch.object(
        firebase_auth,
        "verify_id_token",
        side_effect=firebase_auth.ExpiredIdTokenError("expired", cause=None),
    ):
        with pytest.raises(AuthenticationError, match="expired"):
            await get_current_user(http_creds=_Creds("tok"))


async def test_invalid_token_raises_authentication_error() -> None:
    with patch.object(
        firebase_auth,
        "verify_id_token",
        side_effect=firebase_auth.InvalidIdTokenError("bad"),
    ):
        with pytest.raises(AuthenticationError, match="Invalid authorization token"):
            await get_current_user(http_creds=_Creds("tok"))


async def test_unexpected_error_is_wrapped_as_authentication_error() -> None:
    with patch.object(firebase_auth, "verify_id_token", side_effect=RuntimeError("kaboom")):
        with pytest.raises(AuthenticationError, match="Token verification failed"):
            await get_current_user(http_creds=_Creds("tok"))


# ── require_admin / require_superadmin ──────────────────────────────────────────


async def test_require_admin_allows_admin(admin_user: AuthenticatedUser) -> None:
    assert await require_admin(user=admin_user) is admin_user


async def test_require_admin_rejects_plain_user(user: AuthenticatedUser) -> None:
    with pytest.raises(AuthorizationError, match="Administrator access"):
        await require_admin(user=user)


async def test_require_superadmin_rejects_admin(admin_user: AuthenticatedUser) -> None:
    with pytest.raises(AuthorizationError, match="Superadmin access"):
        await require_superadmin(user=admin_user)


async def test_require_superadmin_allows_superadmin() -> None:
    su = AuthenticatedUser("s1", "s@x.com", True, "S", "password", role=ROLE_SUPERADMIN)
    assert await require_superadmin(user=su) is su
