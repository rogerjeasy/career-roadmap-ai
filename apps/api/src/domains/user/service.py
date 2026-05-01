"""User domain — business logic and Firebase Auth integration."""
import httpx
from firebase_admin import auth as firebase_auth
from fastapi import Depends

from src.config import settings
from src.core.auth import AuthenticatedUser
from src.core.exceptions import AuthenticationError, ConflictError, ExternalServiceError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.http import get_http_client
from src.domains.user.model import User
from src.domains.user.firestore_repository import FirestoreUserRepository

logger = get_logger(__name__)

PROVIDER_PASSWORD = "password"
PROVIDER_GOOGLE = "google.com"

_FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1"
_FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1"

_FIREBASE_ERROR_MAP: dict[str, str] = {
    "EMAIL_EXISTS": "Email address is already in use",
    "INVALID_PASSWORD": "Invalid email or password",
    "EMAIL_NOT_FOUND": "Invalid email or password",
    "USER_DISABLED": "This account has been disabled",
    "INVALID_REFRESH_TOKEN": "Invalid or expired refresh token",
    "TOKEN_EXPIRED": "Session expired — please log in again",
    "USER_NOT_FOUND": "Invalid email or password",
    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many failed attempts — try again later",
}


class UserService:
    def __init__(self, repo: FirestoreUserRepository, http: httpx.AsyncClient) -> None:
        self.repo = repo
        self.http = http

    # ── Registration ──────────────────────────────────────────────────────────

    async def register_with_email(
        self,
        email: str,
        password: str,
        display_name: str | None,
    ) -> tuple[User, str, str, int]:
        """
        Register a new user with email and password.

        Creates the user in Firebase Auth, then writes the profile to Firestore.
        Rolls back Firebase user creation if the Firestore write fails.
        Returns (user, id_token, refresh_token, expires_in).
        """
        existing = await self.repo.get_by_email(email)
        if existing:
            raise ConflictError("Email address is already registered")

        firebase_uid: str | None = None
        try:
            firebase_user = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=False,
            )
            firebase_uid = firebase_user.uid

            id_token, refresh_token, expires_in = await self._sign_in_with_email(email, password)

            user = await self.repo.upsert(
                firebase_uid=firebase_uid,
                email=email,
                provider=PROVIDER_PASSWORD,
                display_name=display_name,
                email_verified=False,
            )
            logger.info("user.registered", uid=firebase_uid, email=email)
            return user, id_token, refresh_token, expires_in

        except (ConflictError, AuthenticationError, ExternalServiceError):
            raise
        except firebase_auth.EmailAlreadyExistsError:
            raise ConflictError("Email address is already registered")
        except Exception:
            if firebase_uid:
                try:
                    firebase_auth.delete_user(firebase_uid)
                except Exception:
                    logger.error("user.firebase_cleanup_failed", uid=firebase_uid)
            raise

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login_with_email(
        self,
        email: str,
        password: str,
    ) -> tuple[User, str, str, int]:
        """
        Sign in with email and password via Firebase REST API.

        Returns (user, id_token, refresh_token, expires_in).
        """
        id_token, refresh_token, expires_in = await self._sign_in_with_email(email, password)

        decoded = firebase_auth.verify_id_token(id_token)
        user = await self.repo.upsert(
            firebase_uid=decoded["uid"],
            email=email,
            provider=PROVIDER_PASSWORD,
            display_name=decoded.get("name"),
            photo_url=decoded.get("picture"),
            email_verified=decoded.get("email_verified", False),
        )
        logger.info("user.login_email", uid=decoded["uid"])
        return user, id_token, refresh_token, expires_in

    async def login_with_google(self, auth_user: AuthenticatedUser) -> User:
        """
        Sync a Google-authenticated user into Firestore after client-side Firebase sign-in.
        """
        if not auth_user.email:
            raise AuthenticationError("Google account must have an email address")

        user = await self.repo.upsert(
            firebase_uid=auth_user.uid,
            email=auth_user.email,
            provider=PROVIDER_GOOGLE,
            display_name=auth_user.name,
            email_verified=auth_user.email_verified,
        )
        logger.info("user.login_google", uid=auth_user.uid)
        return user

    # ── Token management ──────────────────────────────────────────────────────

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str, int]:
        """Exchange a Firebase refresh token for a new ID token."""
        resp = await self.http.post(
            f"{_FIREBASE_TOKEN_URL}/token",
            params={"key": settings.firebase_web_api_key},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        if resp.status_code != 200:
            error_code = resp.json().get("error", {}).get("message", "")
            msg = _FIREBASE_ERROR_MAP.get(error_code, "Invalid or expired refresh token")
            raise AuthenticationError(msg)

        data = resp.json()
        return data["id_token"], data["refresh_token"], int(data["expires_in"])

    async def logout(self, uid: str) -> None:
        """Revoke all Firebase refresh tokens for this user."""
        firebase_auth.revoke_refresh_tokens(uid)
        logger.info("user.logout", uid=uid)

    # ── Profile ───────────────────────────────────────────────────────────────

    async def get_profile(self, auth_user: AuthenticatedUser) -> User:
        """Return the Firestore user document, auto-provisioning on first call."""
        user = await self.repo.get_by_firebase_uid(auth_user.uid)
        if user is None:
            user = await self.repo.upsert(
                firebase_uid=auth_user.uid,
                email=auth_user.email or "",
                provider=auth_user.sign_in_provider,
                display_name=auth_user.name,
                email_verified=auth_user.email_verified,
            )
        return user

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _sign_in_with_email(self, email: str, password: str) -> tuple[str, str, int]:
        """Call Firebase REST API signInWithPassword. Returns (id_token, refresh_token, expires_in)."""
        resp = await self.http.post(
            f"{_FIREBASE_AUTH_URL}/accounts:signInWithPassword",
            params={"key": settings.firebase_web_api_key},
            json={"email": email, "password": password, "returnSecureToken": True},
        )
        if resp.status_code != 200:
            error_code = resp.json().get("error", {}).get("message", "")
            msg = _FIREBASE_ERROR_MAP.get(error_code, "Authentication failed")
            raise AuthenticationError(msg)

        data = resp.json()
        return data["idToken"], data["refreshToken"], int(data["expiresIn"])


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_user_service(
    http: httpx.AsyncClient = Depends(get_http_client),
) -> UserService:
    db = get_firestore_client()
    return UserService(repo=FirestoreUserRepository(db), http=http)
