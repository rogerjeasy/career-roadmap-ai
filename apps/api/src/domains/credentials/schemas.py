"""Verifiable Skill Credentials domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CredentialLevel = Literal["beginner", "intermediate", "advanced", "expert"]
CredentialStatus = Literal["active", "revoked"]

_VALID_LEVELS = ("beginner", "intermediate", "advanced", "expert")


class CredentialEvidenceRef(BaseModel):
    """A frozen snapshot of an Evidence Vault item embedded in a credential.

    Stored by value (not by reference) so the credential remains verifiable and
    self-contained even if the source evidence is later edited or deleted.
    """

    evidence_id: str
    title: str
    type: str
    link: str = ""
    date_label: str = ""


class CredentialIssue(BaseModel):
    """Request body for minting a new credential."""

    skill: str = Field(min_length=1, max_length=120)
    level: CredentialLevel = "intermediate"
    summary: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class CredentialOut(BaseModel):
    id: str
    skill: str
    level: CredentialLevel
    summary: str
    holder_name: str
    evidence: list[CredentialEvidenceRef]
    status: CredentialStatus
    signature: str
    share_token: str
    verify_url: str
    issued_at: datetime | None = None
    revoked_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any], verify_url: str) -> "CredentialOut":
        level = doc.get("level", "intermediate")
        status = doc.get("status", "active")
        raw_evidence = doc.get("evidence") or []
        evidence = [
            CredentialEvidenceRef(
                evidence_id=str(e.get("evidence_id", "")),
                title=str(e.get("title", "")),
                type=str(e.get("type", "other")),
                link=str(e.get("link", "")),
                date_label=str(e.get("date_label", "")),
            )
            for e in raw_evidence
            if isinstance(e, dict)
        ]
        return cls(
            id=doc.get("id", ""),
            skill=doc.get("skill", ""),
            level=level if level in _VALID_LEVELS else "intermediate",
            summary=doc.get("summary", ""),
            holder_name=doc.get("holder_name", ""),
            evidence=evidence,
            status="revoked" if status == "revoked" else "active",
            signature=doc.get("signature", ""),
            share_token=doc.get("share_token", ""),
            verify_url=verify_url,
            issued_at=doc.get("created_at"),
            revoked_at=doc.get("revoked_at"),
        )


class CredentialVerification(BaseModel):
    """Public verification result returned for a share token (no auth)."""

    valid: bool
    status: CredentialStatus | None = None
    reason: str
    skill: str | None = None
    level: CredentialLevel | None = None
    summary: str | None = None
    holder_name: str | None = None
    evidence_count: int = 0
    evidence: list[CredentialEvidenceRef] = Field(default_factory=list)
    issued_at: datetime | None = None
    revoked_at: datetime | None = None
