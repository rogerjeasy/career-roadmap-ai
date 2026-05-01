"""Firebase Auth — token verification and FastAPI dependency."""
import json
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings
from src.core.exceptions import AuthenticationError
from src.core.logging import get_logger

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None
    sign_in_provider: str  # Firebase provider ID: "password", "google.com", etc.


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

    return AuthenticatedUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        email_verified=decoded.get("email_verified", False),
        name=decoded.get("name"),
        sign_in_provider=decoded.get("firebase", {}).get("sign_in_provider", "password"),
    )
