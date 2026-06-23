"""Unit tests for NotificationService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.notifications.schemas import NotificationCreate, NotificationOut
from src.domains.notifications.service import NotificationService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.count_unread = AsyncMock(return_value=3)
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "n1", "created_at": NOW, **doc})
    r.update = AsyncMock(return_value=None)
    r.mark_all_read = AsyncMock(return_value=5)
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo) -> NotificationService:
    return NotificationService(repo)


async def test_create_defaults_read_false(service, repo) -> None:
    out = await service.create("u1", NotificationCreate(title="Hi"))
    assert isinstance(out, NotificationOut)
    assert out.read is False
    _uid, doc = repo.create.call_args.args
    assert doc["read"] is False


async def test_unread_count(service) -> None:
    assert await service.unread_count("u1") == 3


async def test_mark_read_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.mark_read("u1", "missing")


async def test_mark_read_happy(service, repo) -> None:
    repo.update = AsyncMock(return_value={"id": "n1", "read": True, "created_at": NOW})
    out = await service.mark_read("u1", "n1")
    assert out.read is True


async def test_mark_all_read_returns_count(service) -> None:
    assert await service.mark_all_read("u1") == 5


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
