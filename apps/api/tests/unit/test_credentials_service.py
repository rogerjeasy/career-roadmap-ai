"""Unit tests for CredentialService (signing + verification round-trip)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.credentials.schemas import CredentialIssue
from src.domains.credentials.service import CredentialService

pytestmark = pytest.mark.unit


class FakeRepo:
    def __init__(self) -> None:
        self.by_token: dict[str, dict] = {}
        self.by_id: dict[str, dict] = {}
        self._seq = 0

    async def create(self, uid, doc):
        self._seq += 1
        d = {"id": f"c{self._seq}", "user_id": uid, **doc}
        self.by_token[doc["share_token"]] = d
        self.by_id[d["id"]] = d
        return d

    async def get_by_token(self, token):
        return self.by_token.get(token)

    async def get(self, cid, uid):
        return self.by_id.get(cid)

    async def update(self, cid, uid, patch):
        if cid not in self.by_id:
            return None
        self.by_id[cid].update(patch)
        return self.by_id[cid]

    async def soft_delete(self, cid, uid):
        return self.by_id.pop(cid, None) is not None

    async def list_for_user(self, uid, limit=100):
        return list(self.by_id.values())


@pytest.fixture
def evidence() -> MagicMock:
    e = MagicMock()
    e.get = AsyncMock(return_value={"id": "e1", "title": "Shipped", "type": "project", "link": "u"})
    return e


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def service(repo, evidence) -> CredentialService:
    return CredentialService(repo, evidence)


async def test_issue_requires_evidence(service, evidence) -> None:
    evidence.get = AsyncMock(return_value=None)
    with pytest.raises(ValidationError):
        await service.issue("u1", "Ada", CredentialIssue(skill="SQL", evidence_ids=["e1"]))


async def test_issue_then_verify_is_valid(service) -> None:
    cred = await service.issue("u1", "Ada", CredentialIssue(skill="SQL", evidence_ids=["e1"]))
    assert cred.status == "active"
    assert cred.verify_url.endswith(cred.share_token)
    result = await service.verify(cred.share_token)
    assert result.valid is True
    assert result.skill == "SQL"


async def test_verify_unknown_token_is_invalid(service) -> None:
    result = await service.verify("does-not-exist")
    assert result.valid is False


async def test_verify_detects_tampering(service, repo) -> None:
    cred = await service.issue("u1", "Ada", CredentialIssue(skill="SQL", evidence_ids=["e1"]))
    repo.by_token[cred.share_token]["skill"] = "Rust"  # tamper after signing
    result = await service.verify(cred.share_token)
    assert result.valid is False
    assert "signature" in result.reason.lower()


async def test_revoked_credential_verifies_as_invalid_but_present(service, repo) -> None:
    cred = await service.issue("u1", "Ada", CredentialIssue(skill="SQL", evidence_ids=["e1"]))
    await service.revoke("u1", cred.id)
    result = await service.verify(cred.share_token)
    assert result.valid is False
    assert result.status == "revoked"


async def test_revoke_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.revoke("u1", "missing")


async def test_delete_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
