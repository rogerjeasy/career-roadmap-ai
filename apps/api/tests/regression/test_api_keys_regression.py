"""Regression tests for the API Keys domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.api_keys.schemas import ApiKeyCreate, ApiKeyOut
from src.domains.api_keys.service import ApiKeyService, _hash_key

pytestmark = pytest.mark.regression


async def test_raw_secret_is_never_persisted_only_its_hash() -> None:
    # REGRESSION: storing the raw key would let a DB leak impersonate users. Only
    # the SHA-256 hash, a display prefix, and last-4 may ever be persisted.
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=lambda uid, doc: {"id": "k1", "user_id": uid, **doc})
    service = ApiKeyService(repo, MagicMock())

    created = await service.create("u1", ApiKeyCreate(name="k"))
    _uid, stored = repo.create.call_args.args
    assert "key" not in stored
    assert stored["key_hash"] == _hash_key(created.key)
    assert created.key not in stored.values()


def test_list_out_model_has_no_secret_field() -> None:
    # REGRESSION: ApiKeyOut (used by list) must not expose the secret; only the
    # creation-time ApiKeyCreated subclass carries `key`.
    assert "key" not in ApiKeyOut.model_fields


async def test_authenticate_does_not_fail_when_last_used_stamp_write_errors() -> None:
    # REGRESSION: the best-effort last_used_at write must never block auth.
    repo = MagicMock()
    repo.get_by_hash = AsyncMock(return_value={"id": "k1", "user_id": "u9", "revoked": False})
    repo.update = AsyncMock(side_effect=RuntimeError("firestore down"))
    service = ApiKeyService(repo, MagicMock())
    assert await service.authenticate("cra_live_x") == "u9"
