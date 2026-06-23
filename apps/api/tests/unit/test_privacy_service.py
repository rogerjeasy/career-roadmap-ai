"""Unit tests for PrivacyService (export / purge / delete)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.privacy.service import PrivacyService, _USER_COLLECTIONS

pytestmark = pytest.mark.unit


class _FakeRepo:
    """One doc per collection; hard_delete succeeds."""

    def __init__(self, db, name):
        self.name = name

    async def list_for_user(self, uid, limit=0, include_deleted=False):
        return [{"id": f"{self.name}-1", "user_id": uid}]

    async def hard_delete(self, did, uid):
        return True


@pytest.fixture
def users() -> MagicMock:
    u = MagicMock()
    u.delete_account = AsyncMock()
    return u


@pytest.fixture
def service(users) -> PrivacyService:
    return PrivacyService(MagicMock(), users)


async def test_export_includes_every_nonempty_collection(service, monkeypatch) -> None:
    monkeypatch.setattr("src.domains.privacy.service.FirestoreCrudRepository", _FakeRepo)
    bundle = await service.export("u1")
    assert bundle["user_id"] == "u1"
    assert "generated_at" in bundle
    assert len(bundle["collections"]) == len(_USER_COLLECTIONS)


async def test_purge_counts_removed_docs(service, monkeypatch) -> None:
    monkeypatch.setattr("src.domains.privacy.service.FirestoreCrudRepository", _FakeRepo)
    removed = await service.purge_data("u1")
    assert removed == len(_USER_COLLECTIONS)


async def test_purge_is_best_effort_on_failure(service, monkeypatch) -> None:
    class _FlakyRepo(_FakeRepo):
        async def hard_delete(self, did, uid):
            if self.name == "applications":
                raise RuntimeError("firestore error")
            return True

    monkeypatch.setattr("src.domains.privacy.service.FirestoreCrudRepository", _FlakyRepo)
    removed = await service.purge_data("u1")
    # All but the one failing collection are still purged.
    assert removed == len(_USER_COLLECTIONS) - 1


async def test_delete_account_purges_before_deleting_user(service, users, monkeypatch) -> None:
    order: list[str] = []

    class _TrackingRepo(_FakeRepo):
        async def hard_delete(self, did, uid):
            order.append("purge")
            return True

    monkeypatch.setattr("src.domains.privacy.service.FirestoreCrudRepository", _TrackingRepo)
    users.delete_account = AsyncMock(side_effect=lambda uid: order.append("delete_user"))

    await service.delete_account("u1")
    # Data is purged before the account/profile is removed.
    assert order[-1] == "delete_user"
    assert "purge" in order
    users.delete_account.assert_awaited_once_with("u1")
