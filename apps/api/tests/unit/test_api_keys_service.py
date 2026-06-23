"""Unit tests for ApiKeyService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.api_keys.schemas import ApiKeyCreate, ApiKeyCreated
from src.domains.api_keys.service import ApiKeyService, _hash_key

pytestmark = pytest.mark.unit


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "k1", "user_id": uid, **doc})
    r.update = AsyncMock(side_effect=lambda kid, uid, patch: {"id": kid, "user_id": uid, "name": "n", "prefix": "cra_live_ab", "last4": "wxyz", "revoked": patch.get("revoked", False)})
    r.hard_delete = AsyncMock(return_value=True)
    r.get_by_hash = AsyncMock(return_value=None)
    return r


@pytest.fixture
def service(repo: MagicMock) -> ApiKeyService:
    return ApiKeyService(repo, MagicMock())


async def test_create_mints_key_with_live_prefix_and_returns_secret_once(service, repo) -> None:
    created = await service.create("u1", ApiKeyCreate(name="CI key"))
    assert isinstance(created, ApiKeyCreated)
    assert created.key.startswith("cra_live_")
    assert created.last4 == created.key[-4:]
    # The stored doc holds a hash, never the raw secret.
    _uid, doc = repo.create.call_args.args
    assert doc["key_hash"] == _hash_key(created.key)
    assert "key" not in doc


async def test_revoke_sets_revoked_true(service, repo) -> None:
    out = await service.revoke("u1", "k1")
    assert out.revoked is True


async def test_revoke_missing_raises_not_found(service, repo) -> None:
    repo.update = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.revoke("u1", "missing")


async def test_delete_missing_raises_not_found(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


async def test_authenticate_returns_owner_for_valid_key(service, repo) -> None:
    repo.get_by_hash = AsyncMock(return_value={"id": "k1", "user_id": "u9", "revoked": False})
    repo.update = AsyncMock()
    assert await service.authenticate("cra_live_secret") == "u9"


async def test_authenticate_rejects_revoked_key(service, repo) -> None:
    repo.get_by_hash = AsyncMock(return_value={"id": "k1", "user_id": "u9", "revoked": True})
    assert await service.authenticate("cra_live_secret") is None


async def test_authenticate_unknown_key_returns_none(service, repo) -> None:
    repo.get_by_hash = AsyncMock(return_value=None)
    assert await service.authenticate("cra_live_nope") is None


def test_hash_key_is_deterministic_sha256() -> None:
    assert _hash_key("abc") == _hash_key("abc")
    assert _hash_key("abc") != _hash_key("abd")
    assert len(_hash_key("abc")) == 64
