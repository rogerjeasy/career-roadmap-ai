"""Unit tests for PushService (push is unconfigured in the test env)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.push.schemas import PushKeys, PushSubscriptionIn
from src.domains.push.service import PushService

pytestmark = pytest.mark.unit


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock()
    r.hard_delete = AsyncMock()
    r.list_for_user = AsyncMock(return_value=[])
    return r


@pytest.fixture
def service(repo) -> PushService:
    return PushService(repo)


def test_config_disabled_without_vapid_keys(service) -> None:
    cfg = service.config()
    assert cfg.enabled is False
    assert cfg.public_key is None


async def test_subscribe_persists_with_device_id(service, repo) -> None:
    sub = PushSubscriptionIn(endpoint="https://push/abc", keys=PushKeys(p256dh="k", auth="a"))
    await service.subscribe("u1", sub)
    repo.create.assert_awaited_once()
    assert repo.create.call_args.kwargs["doc_id"]  # device id derived from endpoint


async def test_unsubscribe_deletes(service, repo) -> None:
    await service.unsubscribe("u1", "https://push/abc")
    repo.hard_delete.assert_awaited_once()


async def test_send_to_user_degrades_gracefully_when_unconfigured(service) -> None:
    result = await service.send_to_user("u1", title="Hi", body="b")
    assert result.enabled is False
    assert result.sent == 0
    assert result.detail  # explains why


async def test_send_test_uses_send_to_user(service) -> None:
    result = await service.send_test("u1")
    assert result.enabled is False
