"""Verifiable Skill Credentials — pure HMAC signing helpers.

Kept free of Firestore / FastAPI so the signing scheme is trivially unit-testable
and deterministic. The canonical payload pins exactly the fields that constitute
the *claim*: change any of them and the signature no longer matches, which is
how the public verifier detects tampering.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical_payload(
    *,
    user_id: str,
    skill: str,
    level: str,
    holder_name: str,
    evidence: list[dict[str, Any]],
) -> str:
    """Serialise the signed fields into a stable, order-independent JSON string."""
    evidence_ids = sorted(str(e.get("evidence_id", "")) for e in evidence)
    payload = {
        "user_id": user_id,
        "skill": skill.strip().lower(),
        "level": level,
        "holder_name": holder_name.strip(),
        "evidence_ids": evidence_ids,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign(secret: str, payload: str) -> str:
    """Return the hex HMAC-SHA256 of ``payload`` under ``secret``."""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(secret: str, payload: str, signature: str) -> bool:
    """Constant-time check that ``signature`` matches the expected HMAC."""
    expected = sign(secret, payload)
    return hmac.compare_digest(expected, signature or "")
