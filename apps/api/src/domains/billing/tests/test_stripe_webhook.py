"""Unit tests for Stripe webhook signature verification.

Pure crypto — no network, no Stripe SDK.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from src.domains.billing.stripe_client import StripeSignatureError, verify_webhook

_SECRET = "whsec_test_secret"


def _sign(payload: bytes, secret: str = _SECRET, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}".encode() + b"." + payload
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def test_valid_signature_returns_event() -> None:
    payload = json.dumps({"type": "checkout.session.completed", "id": "evt_1"}).encode()
    event = verify_webhook(payload, _sign(payload), _SECRET)
    assert event["type"] == "checkout.session.completed"
    assert event["id"] == "evt_1"


def test_tampered_payload_fails() -> None:
    payload = json.dumps({"type": "a"}).encode()
    header = _sign(payload)
    tampered = json.dumps({"type": "b"}).encode()
    with pytest.raises(StripeSignatureError):
        verify_webhook(tampered, header, _SECRET)


def test_wrong_secret_fails() -> None:
    payload = b'{"type":"x"}'
    with pytest.raises(StripeSignatureError):
        verify_webhook(payload, _sign(payload, secret="whsec_other"), _SECRET)


def test_missing_header_fails() -> None:
    with pytest.raises(StripeSignatureError):
        verify_webhook(b"{}", None, _SECRET)


def test_malformed_header_fails() -> None:
    with pytest.raises(StripeSignatureError):
        verify_webhook(b"{}", "not-a-valid-header", _SECRET)


def test_stale_timestamp_fails() -> None:
    payload = b'{"type":"x"}'
    old = int(time.time()) - 10_000
    with pytest.raises(StripeSignatureError):
        verify_webhook(payload, _sign(payload, timestamp=old), _SECRET)
