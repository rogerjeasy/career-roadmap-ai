"""Regression tests for the Credentials domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.credentials.schemas import CredentialIssue, CredentialOut
from src.domains.credentials.service import CredentialService

pytestmark = pytest.mark.regression


class _Repo:
    def __init__(self):
        self.by_token = {}

    async def create(self, uid, doc):
        d = {"id": "c1", "user_id": uid, **doc}
        self.by_token[doc["share_token"]] = d
        return d

    async def get_by_token(self, token):
        return self.by_token.get(token)


async def test_swapping_the_referenced_evidence_breaks_the_signature() -> None:
    # REGRESSION: the signed claim pins the evidence_ids — swapping in a different
    # evidence item after issuance must make verification fail.
    repo = _Repo()
    evidence = MagicMock()
    evidence.get = AsyncMock(return_value={"id": "e1", "title": "Real", "type": "project"})
    service = CredentialService(repo, evidence)
    cred = await service.issue("u1", "Ada", CredentialIssue(skill="SQL", evidence_ids=["e1"]))

    repo.by_token[cred.share_token]["evidence"][0]["evidence_id"] = "e999"
    result = await service.verify(cred.share_token)
    assert result.valid is False


def test_from_doc_unknown_level_and_status_fall_back() -> None:
    out = CredentialOut.from_doc({"id": "c1", "level": "wizard", "status": "weird"}, "https://x/v/t")
    assert out.level == "intermediate"
    assert out.status == "active"  # only "revoked" is special; everything else → active


async def test_deleted_credential_token_returns_no_credential() -> None:
    # REGRESSION: a soft-deleted credential's share link must report "no credential"
    # rather than leak its contents.
    repo = MagicMock()
    repo.get_by_token = AsyncMock(return_value={"id": "c1", "deleted_at": "2026-01-01", "share_token": "t"})
    service = CredentialService(repo, MagicMock())
    result = await service.verify("t")
    assert result.valid is False
