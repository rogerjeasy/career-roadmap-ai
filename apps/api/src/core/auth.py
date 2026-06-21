"""Firebase Auth — token verification and FastAPI dependency."""
import json
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.core.logging import get_logger

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Roles that may access the admin surface, in ascending privilege order.
# Stored as a Firebase Auth custom claim (``role``) so it is signed into the ID
# token and verified on every request without a database round-trip.
ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
_VALID_ROLES = (ROLE_USER, ROLE_ADMIN, ROLE_SUPERADMIN)
_ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPERADMIN)


@dataclass
class AuthenticatedUser:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None
    sign_in_provider: str  # Firebase provider ID: "password", "google.com", etc.
    role: str = ROLE_USER  # Firebase custom claim; defaults to a normal user.

    @property
    def is_admin(self) -> bool:
        return self.role in _ADMIN_ROLES

    @property
    def is_superadmin(self) -> bool:
        return self.role == ROLE_SUPERADMIN


def init_firebase_app() -> None:
    """Initialise firebase-admin once at startup. Safe to call multiple times."""
    if firebase_admin._apps:
        return

    options: dict = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    if settings.firebase_credentials_path:
        cred = credentials.Certificate(settings.firebase_credentials_path)
    elif settings.firebase_credentials_json:
        cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
    else:
        cred = credentials.ApplicationDefault()

    firebase_admin.initialize_app(cred, options or None)
    logger.info("firebase.init", project=settings.firebase_project_id)


async def get_current_user(
    http_creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency — extracts and verifies Firebase ID token from Bearer header."""
    if http_creds is None or not http_creds.credentials:
        raise AuthenticationError("Missing authorization token")

    try:
        decoded = firebase_auth.verify_id_token(http_creds.credentials, check_revoked=False)
    except firebase_auth.ExpiredIdTokenError:
        raise AuthenticationError("Token has expired")
    except firebase_auth.RevokedIdTokenError:
        raise AuthenticationError("Token has been revoked")
    except firebase_auth.InvalidIdTokenError as exc:
        logger.warning("auth.invalid_token", error=str(exc))
        raise AuthenticationError("Invalid authorization token")
    except Exception as exc:
        logger.error("auth.verify_error", error=str(exc))
        raise AuthenticationError("Token verification failed")

    role = decoded.get("role", ROLE_USER)
    if role not in _VALID_ROLES:
        role = ROLE_USER

    return AuthenticatedUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        email_verified=decoded.get("email_verified", False),
        name=decoded.get("name"),
        sign_in_provider=decoded.get("firebase", {}).get("sign_in_provider", "password"),
        role=role,
    )


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """FastAPI dependency — gate an endpoint to admins and superadmins.

    The role is read from the Firebase custom claim baked into the verified ID
    token (see ``get_current_user``). Raises ``AuthorizationError`` (HTTP 403)
    for any non-admin caller, which the global handler renders as a structured
    JSON error.
    """
    if not user.is_admin:
        logger.warning("admin.access_denied", uid=user.uid, role=user.role)
        raise AuthorizationError("Administrator access is required for this resource")
    return user


async def require_superadmin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """FastAPI dependency — gate an endpoint to superadmins only."""
    if not user.is_superadmin:
        logger.warning("admin.superadmin_required", uid=user.uid, role=user.role)
        raise AuthorizationError("Superadmin access is required for this resource")
    return user
