"""CalendarTokenStore — encrypted server-side OAuth token storage.

Tokens are stored in Redis with Fernet symmetric encryption so the MCP
server can call Google Calendar and Outlook on behalf of users without
requiring a token on every request.

Auto-refresh: when an access_token is expired the store silently refreshes
it using the stored refresh_token (Google + Microsoft OAuth 2.0 flows).
The refreshed token is written back to Redis transparently.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # store for 7 days; token itself may expire sooner
_REFRESH_BUFFER_SECONDS = 60  # refresh 60 s before actual expiry


class TokenRefreshError(Exception):
    pass


class CalendarTokenStore:
    """Encrypted Redis-backed store for per-user, per-provider OAuth tokens."""

    def __init__(
        self,
        redis_url: str,
        encryption_key: str | None,
        google_client_id: str | None,
        google_client_secret: str | None,
        microsoft_client_id: str | None,
        microsoft_client_secret: str | None,
    ) -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._fernet: Any = None
        self._google_client_id = google_client_id
        self._google_client_secret = google_client_secret
        self._microsoft_client_id = microsoft_client_id
        self._microsoft_client_secret = microsoft_client_secret

        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                self._fernet = Fernet(encryption_key.encode())
            except Exception as exc:
                logger.warning("token_store.invalid_encryption_key", error=str(exc))

    async def connect(self) -> None:
        from redis.asyncio import from_url
        self._redis = from_url(self._redis_url, decode_responses=False)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    # ── Storage helpers ───────────────────────────────────────────────────────

    def _redis_key(self, user_id: str, provider: str) -> str:
        return f"calendar:token:{user_id}:{provider}"

    def _encrypt(self, data: bytes) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(data)
        return data

    def _decrypt(self, data: bytes) -> bytes:
        if self._fernet:
            from cryptography.fernet import InvalidToken
            try:
                return self._fernet.decrypt(data)
            except InvalidToken as exc:
                raise ValueError("Token decryption failed — key mismatch or corrupt data") from exc
        return data

    # ── Public API ────────────────────────────────────────────────────────────

    async def store(
        self,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: str = "",
        expires_in: int = 3600,
    ) -> None:
        if not self._redis:
            raise RuntimeError("Token store not connected — call connect() first")

        payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + expires_in - _REFRESH_BUFFER_SECONDS,
        }
        raw = json.dumps(payload).encode()
        encrypted = self._encrypt(raw)
        await self._redis.setex(self._redis_key(user_id, provider), _TOKEN_TTL_SECONDS, encrypted)
        logger.info("token_store.stored", user_id=user_id, provider=provider)

    async def get_access_token(self, user_id: str, provider: str) -> str | None:
        """Return a valid access token, auto-refreshing if expired. None if not stored."""
        if not self._redis:
            return None

        raw = await self._redis.get(self._redis_key(user_id, provider))
        if not raw:
            return None

        try:
            decrypted = self._decrypt(raw)
            payload: dict[str, Any] = json.loads(decrypted)
        except Exception as exc:
            logger.warning("token_store.decrypt_failed", error=str(exc), user_id=user_id)
            return None

        access_token: str = payload.get("access_token", "")
        expires_at: float = payload.get("expires_at", 0)

        if time.time() < expires_at and access_token:
            return access_token

        refresh_token: str = payload.get("refresh_token", "")
        if not refresh_token:
            logger.info("token_store.expired_no_refresh", user_id=user_id, provider=provider)
            return None

        try:
            new_tokens = await self._refresh(provider, refresh_token)
        except TokenRefreshError as exc:
            logger.warning("token_store.refresh_failed", error=str(exc), user_id=user_id)
            return None

        await self.store(
            user_id,
            provider,
            access_token=new_tokens["access_token"],
            refresh_token=new_tokens.get("refresh_token") or refresh_token,
            expires_in=int(new_tokens.get("expires_in", 3600)),
        )
        logger.info("token_store.refreshed", user_id=user_id, provider=provider)
        return new_tokens["access_token"]

    async def delete(self, user_id: str, provider: str) -> None:
        if self._redis:
            await self._redis.delete(self._redis_key(user_id, provider))
            logger.info("token_store.deleted", user_id=user_id, provider=provider)

    # ── OAuth refresh ─────────────────────────────────────────────────────────

    async def _refresh(self, provider: str, refresh_token: str) -> dict[str, Any]:
        if provider == "google":
            return await self._refresh_google(refresh_token)
        if provider == "outlook":
            return await self._refresh_microsoft(refresh_token)
        raise TokenRefreshError(f"Unknown provider for refresh: {provider!r}")

    async def _refresh_google(self, refresh_token: str) -> dict[str, Any]:
        if not self._google_client_id or not self._google_client_secret:
            raise TokenRefreshError("GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not set")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._google_client_id,
                    "client_secret": self._google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code != 200:
            raise TokenRefreshError(
                f"Google token refresh HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if "error" in data:
            raise TokenRefreshError(
                f"Google refresh error: {data.get('error_description') or data['error']}"
            )
        return data

    async def _refresh_microsoft(self, refresh_token: str) -> dict[str, Any]:
        if not self._microsoft_client_id or not self._microsoft_client_secret:
            raise TokenRefreshError(
                "MICROSOFT_OAUTH_CLIENT_ID / MICROSOFT_OAUTH_CLIENT_SECRET not set"
            )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _MICROSOFT_TOKEN_URL,
                data={
                    "client_id": self._microsoft_client_id,
                    "client_secret": self._microsoft_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "Calendars.ReadWrite offline_access",
                },
            )

        if resp.status_code != 200:
            raise TokenRefreshError(
                f"Microsoft token refresh HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if "error" in data:
            raise TokenRefreshError(
                f"Microsoft refresh error: {data.get('error_description') or data['error']}"
            )
        return data
