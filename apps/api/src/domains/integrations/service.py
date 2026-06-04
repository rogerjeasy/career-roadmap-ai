"""Integrations domain — OAuth connect / callback / disconnect.

Flow:
  1. ``build_authorize_url`` — generate a CSRF ``state`` (stored in Redis, bound
     to the user + provider) and return the provider's authorize URL.
  2. ``handle_callback`` — validate ``state``, exchange ``code`` for tokens, fetch
     a best-effort account label, encrypt + persist the connection.
  3. ``disconnect`` — delete the stored connection.

Every connect / disconnect emits a structured audit log event.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient
from redis.asyncio import Redis

from src.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.http import get_http_client
from src.db.redis import get_redis
from src.domains.integrations.crypto import encrypt_token
from src.domains.integrations.firestore_repository import FirestoreIntegrationRepository
from src.domains.integrations.providers import (
    ProviderSpec,
    all_specs,
    get_provider_spec,
)
from src.domains.integrations.schemas import IntegrationStatusOut

logger = get_logger(__name__)

_STATE_TTL_SECONDS = 600  # 10 minutes to complete the OAuth round-trip
_STATE_PREFIX = "oauth_state:"


class IntegrationsService:
    def __init__(
        self,
        settings: Settings,
        repo: FirestoreIntegrationRepository,
        redis: Redis,
        http: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._redis = redis
        self._http = http

    # ── Status ──────────────────────────────────────────────────────────────--

    async def list_status(self, user_id: str) -> list[IntegrationStatusOut]:
        out: list[IntegrationStatusOut] = []
        for spec in all_specs():
            doc = await self._repo.get(self._repo.doc_id(user_id, spec.key), user_id)
            connected = bool(doc and doc.get("access_token"))
            out.append(
                IntegrationStatusOut(
                    provider=spec.key,
                    name=spec.name,
                    description=spec.description,
                    consent_note=spec.consent_note,
                    available=spec.is_available(self._settings),
                    connected=connected,
                    account_label=(doc or {}).get("account_label") if connected else None,
                    connected_at=(doc or {}).get("connected_at") if connected else None,
                    scopes=list((doc or {}).get("scopes", [])) if connected else [],
                )
            )
        return out

    # ── Connect (authorize) ─────────────────────────────────────────────────--

    def _redirect_uri(self, provider: str) -> str:
        base = self._settings.oauth_callback_base_url.rstrip("/")
        return f"{base}/api/v1/integrations/{provider}/callback"

    async def build_authorize_url(self, user_id: str, provider: str) -> str:
        spec = self._require_available(provider)
        state = secrets.token_urlsafe(32)
        await self._redis.set(
            f"{_STATE_PREFIX}{state}",
            json.dumps({"user_id": user_id, "provider": provider}),
            ex=_STATE_TTL_SECONDS,
        )
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": spec.client_id(self._settings) or "",
            "redirect_uri": self._redirect_uri(provider),
            "scope": " ".join(spec.scopes),
            "state": state,
            **spec.extra_authorize_params,
        }
        url = str(httpx.URL(spec.authorize_url, params=params))
        logger.info("integrations.authorize_url_built", user_id=user_id, provider=provider)
        return url

    # ── Callback ───────────────────────────────────────────────────────────--

    async def handle_callback(self, provider: str, code: str, state: str) -> str:
        """Validate state, exchange the code, persist the connection.

        Returns the ``user_id`` the connection was stored for so the caller can
        redirect the browser back to the app.
        """
        spec = self._require_available(provider)

        raw = await self._redis.get(f"{_STATE_PREFIX}{state}")
        if not raw:
            raise ValidationError("OAuth state is invalid or has expired. Please try again.")
        await self._redis.delete(f"{_STATE_PREFIX}{state}")

        payload = json.loads(raw)
        if payload.get("provider") != provider:
            raise ValidationError("OAuth state does not match the provider.")
        user_id = str(payload["user_id"])

        token = await self._exchange_code(spec, code)
        access_token = str(token.get("access_token", ""))
        if not access_token:
            raise ExternalServiceError(f"{spec.name} did not return an access token.")
        refresh_token = token.get("refresh_token")
        expires_in = token.get("expires_in")
        granted_scope = token.get("scope")

        account_label = await self._fetch_account_label(spec, access_token)

        expires_at: datetime | None = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        scopes = (
            granted_scope.split() if isinstance(granted_scope, str) and granted_scope else spec.scopes
        )

        data: dict[str, Any] = {
            "provider": provider,
            "access_token": encrypt_token(self._settings, access_token),
            "refresh_token": (
                encrypt_token(self._settings, str(refresh_token)) if refresh_token else None
            ),
            "scopes": scopes,
            "account_label": account_label,
            "connected_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
        }

        doc_id = self._repo.doc_id(user_id, provider)
        existing = await self._repo.get(doc_id, user_id)
        if existing is None:
            await self._repo.create(user_id, data, doc_id=doc_id)
        else:
            await self._repo.update(doc_id, user_id, data)

        logger.info(
            "integrations.connected",
            user_id=user_id,
            provider=provider,
            account_label=account_label,
        )
        return user_id

    async def disconnect(self, user_id: str, provider: str) -> None:
        if get_provider_spec(provider) is None:
            raise NotFoundError(f"Unknown integration provider '{provider}'.")
        deleted = await self._repo.hard_delete(self._repo.doc_id(user_id, provider), user_id)
        logger.info(
            "integrations.disconnected",
            user_id=user_id,
            provider=provider,
            existed=deleted,
        )

    # ── Internals ──────────────────────────────────────────────────────────--

    def _require_available(self, provider: str) -> ProviderSpec:
        spec = get_provider_spec(provider)
        if spec is None:
            raise NotFoundError(f"Unknown integration provider '{provider}'.")
        if not spec.is_available(self._settings):
            raise ValidationError(
                f"{spec.name} integration is not configured on the server."
            )
        return spec

    async def _exchange_code(self, spec: ProviderSpec, code: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri(spec.key),
            "client_id": spec.client_id(self._settings),
            "client_secret": spec.client_secret(self._settings),
        }
        try:
            resp = await self._http.post(
                spec.token_url,
                data=data,
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "integrations.token_exchange_failed", provider=spec.key, error=str(exc)
            )
            raise ExternalServiceError(
                f"Could not complete the {spec.name} connection."
            ) from exc
        return resp.json()

    async def _fetch_account_label(self, spec: ProviderSpec, access_token: str) -> str | None:
        """Best-effort human-readable account label; never fatal."""
        if not spec.userinfo_url:
            return None
        try:
            resp = await self._http.get(
                spec.userinfo_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            info = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "integrations.userinfo_failed", provider=spec.key, error=str(exc)
            )
            return None
        # GitHub → "login"; OIDC providers → "email" / "name".
        for field in ("login", "email", "name", "preferred_username"):
            value = info.get(field)
            if value:
                return str(value)
        return None


async def get_integrations_service(
    db: AsyncClient = Depends(get_firestore_client),
    redis: Redis = Depends(get_redis),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> IntegrationsService:
    return IntegrationsService(
        get_settings(),
        FirestoreIntegrationRepository(db),
        redis,
        http,
    )
