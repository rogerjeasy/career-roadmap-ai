"""Verifiable Skill Credentials — service layer.

Mints credentials that embed *real* evidence the user owns (looked up from the
Evidence Vault, ownership-checked), signs each one over its canonical claim, and
exposes a public, auth-free verifier keyed by share token. Revocation flips the
status without deleting the record, so a shared link resolves to an honest
"revoked" result rather than a dead 404.
"""
from __future__ import annotations

import secrets as secretslib

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.config import settings
from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.credentials import signing
from src.domains.credentials.firestore_repository import FirestoreCredentialRepository
from src.domains.credentials.schemas import (
    CredentialIssue,
    CredentialOut,
    CredentialVerification,
)

logger = get_logger(__name__)


class CredentialService:
    def __init__(
        self,
        repo: FirestoreCredentialRepository,
        evidence: FirestoreCrudRepository,
    ) -> None:
        self._repo = repo
        self._evidence = evidence
        self._secret = settings.credential_signing_secret.get_secret_value()

    # ── URL helpers ───────────────────────────────────────────────────────────

    def _verify_url(self, share_token: str) -> str:
        base = settings.frontend_base_url.rstrip("/")
        return f"{base}/verify/{share_token}"

    def _out(self, doc: dict) -> CredentialOut:
        return CredentialOut.from_doc(doc, self._verify_url(doc.get("share_token", "")))

    # ── Public API ────────────────────────────────────────────────────────────

    async def list(self, user_id: str) -> list[CredentialOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [self._out(d) for d in docs]

    async def get(self, user_id: str, credential_id: str) -> CredentialOut:
        doc = await self._repo.get(credential_id, user_id)
        if doc is None:
            raise NotFoundError("Credential not found.")
        return self._out(doc)

    async def issue(
        self, user_id: str, holder_name: str, payload: CredentialIssue
    ) -> CredentialOut:
        evidence = await self._snapshot_evidence(user_id, payload.evidence_ids)
        if not evidence:
            raise ValidationError(
                "A credential must reference at least one evidence item you own."
            )

        canonical = signing.canonical_payload(
            user_id=user_id,
            skill=payload.skill,
            level=payload.level,
            holder_name=holder_name,
            evidence=[e.copy() for e in evidence],
        )
        signature = signing.sign(self._secret, canonical)
        share_token = secretslib.token_urlsafe(24)

        doc = await self._repo.create(
            user_id,
            {
                "skill": payload.skill.strip(),
                "level": payload.level,
                "summary": payload.summary.strip(),
                "holder_name": holder_name.strip(),
                "evidence": evidence,
                "status": "active",
                "signature": signature,
                "share_token": share_token,
                "revoked_at": None,
            },
        )
        logger.info(
            "credential.issued",
            user_id=user_id,
            credential_id=doc["id"],
            skill=payload.skill,
            evidence_count=len(evidence),
        )
        return self._out(doc)

    async def revoke(self, user_id: str, credential_id: str) -> CredentialOut:
        doc = await self._repo.update(
            credential_id, user_id, {"status": "revoked", "revoked_at": utcnow()}
        )
        if doc is None:
            raise NotFoundError("Credential not found.")
        logger.info("credential.revoked", user_id=user_id, credential_id=credential_id)
        return self._out(doc)

    async def delete(self, user_id: str, credential_id: str) -> None:
        removed = await self._repo.soft_delete(credential_id, user_id)
        if not removed:
            raise NotFoundError("Credential not found.")

    async def verify(self, share_token: str) -> CredentialVerification:
        """Public, auth-free verification of a credential by its share token."""
        doc = await self._repo.get_by_token(share_token)
        if doc is None or doc.get("deleted_at") is not None:
            return CredentialVerification(
                valid=False, reason="No credential exists for this link."
            )

        evidence = [e for e in (doc.get("evidence") or []) if isinstance(e, dict)]
        canonical = signing.canonical_payload(
            user_id=str(doc.get("user_id", "")),
            skill=str(doc.get("skill", "")),
            level=str(doc.get("level", "intermediate")),
            holder_name=str(doc.get("holder_name", "")),
            evidence=evidence,
        )
        signature_ok = signing.verify(self._secret, canonical, str(doc.get("signature", "")))
        if not signature_ok:
            return CredentialVerification(
                valid=False,
                reason="This credential's signature does not match its contents.",
            )

        out = CredentialOut.from_doc(doc, self._verify_url(share_token))
        revoked = out.status == "revoked"
        return CredentialVerification(
            valid=not revoked,
            status=out.status,
            reason=(
                "This credential has been revoked by its holder."
                if revoked
                else "Issued by Career Roadmap AI and verified intact."
            ),
            skill=out.skill,
            level=out.level,
            summary=out.summary,
            holder_name=out.holder_name,
            evidence_count=len(out.evidence),
            evidence=out.evidence,
            issued_at=out.issued_at,
            revoked_at=out.revoked_at,
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _snapshot_evidence(
        self, user_id: str, evidence_ids: list[str]
    ) -> list[dict]:
        """Freeze owner-verified evidence items into embeddable snapshots."""
        out: list[dict] = []
        seen: set[str] = set()
        for eid in evidence_ids:
            if eid in seen:
                continue
            seen.add(eid)
            item = await self._evidence.get(eid, user_id)
            if item is None:
                continue
            out.append(
                {
                    "evidence_id": item["id"],
                    "title": str(item.get("title", "")),
                    "type": str(item.get("type", "other")),
                    "link": str(item.get("link", "")),
                    "date_label": str(item.get("date_label", "")),
                }
            )
        return out


async def get_credential_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> CredentialService:
    return CredentialService(
        FirestoreCredentialRepository(db),
        FirestoreCrudRepository(db, "evidence"),
    )
