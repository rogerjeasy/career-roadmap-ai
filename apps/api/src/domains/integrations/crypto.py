"""Symmetric encryption for OAuth tokens stored at rest.

Uses Fernet (AES-128-CBC + HMAC) keyed by ``settings.integration_token_key``.
If no key is configured the helpers raise ``ConfigurationError`` — connecting an
integration is then refused rather than storing tokens in plaintext.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from src.config import Settings
from src.core.exceptions import AppException


class IntegrationConfigError(AppException):
    error_code = "integration_not_configured"
    status_code = 503


def _fernet(settings: Settings) -> Fernet:
    key = settings.integration_token_key
    if key is None:
        raise IntegrationConfigError(
            "Integration token encryption key is not configured. Set "
            "INTEGRATION_TOKEN_KEY to enable connecting external accounts."
        )
    try:
        return Fernet(key.get_secret_value().encode())
    except (ValueError, TypeError) as exc:  # malformed key
        raise IntegrationConfigError(
            "INTEGRATION_TOKEN_KEY is not a valid Fernet key."
        ) from exc


def encrypt_token(settings: Settings, plaintext: str) -> str:
    return _fernet(settings).encrypt(plaintext.encode()).decode()


def decrypt_token(settings: Settings, ciphertext: str) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None
