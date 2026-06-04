"""OAuth provider registry for external integrations.

Each provider is described declaratively (endpoints, scopes, how to read its
client credentials from settings). A provider is only *available* to connect
when both its client id and secret are configured — otherwise the UI surfaces it
as "not yet configured" rather than offering a broken Connect button.

No provider tokens or secrets are hard-coded here; everything is read from
validated ``Settings``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.config import Settings

IntegrationProvider = Literal["github", "linkedin", "calendar"]

PROVIDERS: tuple[IntegrationProvider, ...] = ("github", "linkedin", "calendar")


@dataclass(frozen=True)
class ProviderSpec:
    key: IntegrationProvider
    name: str
    description: str
    consent_note: str
    authorize_url: str
    token_url: str
    scopes: list[str]
    # Endpoint that returns a human-readable account label (best-effort).
    userinfo_url: str | None
    # Extra params appended to the authorize URL (e.g. Google offline access).
    extra_authorize_params: dict[str, str]

    def client_id(self, settings: Settings) -> str | None:
        return getattr(settings, f"{_CRED_PREFIX[self.key]}_client_id", None)

    def client_secret(self, settings: Settings) -> str | None:
        secret = getattr(settings, f"{_CRED_PREFIX[self.key]}_client_secret", None)
        return secret.get_secret_value() if secret is not None else None

    def is_available(self, settings: Settings) -> bool:
        return bool(self.client_id(settings) and self.client_secret(settings))


# Maps provider key → the Settings field prefix that holds its credentials.
_CRED_PREFIX: dict[IntegrationProvider, str] = {
    "github": "github",
    "linkedin": "linkedin",
    "calendar": "google",
}


_SPECS: dict[IntegrationProvider, ProviderSpec] = {
    "github": ProviderSpec(
        key="github",
        name="GitHub",
        description="Use your repositories as portfolio evidence.",
        consent_note="We read your public profile and public repository metadata only. We never write to your repositories.",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=["read:user"],
        userinfo_url="https://api.github.com/user",
        extra_authorize_params={},
    ),
    "linkedin": ProviderSpec(
        key="linkedin",
        name="LinkedIn",
        description="Import your profile and surface relevant connections.",
        consent_note="We read your basic profile and email. We never post on your behalf.",
        authorize_url="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        scopes=["openid", "profile", "email"],
        userinfo_url="https://api.linkedin.com/v2/userinfo",
        extra_authorize_params={},
    ),
    "calendar": ProviderSpec(
        key="calendar",
        name="Calendar",
        description="Let your coach schedule study blocks and reviews.",
        consent_note="Calendar writes always require a confirmation step before any event is created.",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=[
            "openid",
            "email",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        # Request a refresh token and force the consent screen so we always get one.
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    ),
}


def get_provider_spec(provider: str) -> ProviderSpec | None:
    if provider not in PROVIDERS:
        return None
    return _SPECS[provider]  # type: ignore[index]


def all_specs() -> list[ProviderSpec]:
    return [_SPECS[p] for p in PROVIDERS]
