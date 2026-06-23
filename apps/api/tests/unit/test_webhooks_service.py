"""Unit tests for WebhookService (signed delivery + dispatch routing)."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.exceptions import NotFoundError
from src.domains.webhooks.schemas import WebhookCreate, WebhookCreated
from src.domains.webhooks.service import WebhookService, _sign, _subscribed

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "w1", **doc})
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock()
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def http() -> MagicMock:
    h = MagicMock()
    h.post = AsyncMock(return_value=_Resp(200))
    return h


@pytest.fixture
def service(repo, http) -> WebhookService:
    return WebhookService(repo, http)


def test_subscribed_helper() -> None:
    assert _subscribed(["*"], "anything") is True
    assert _subscribed(["roadmap.updated"], "roadmap.updated") is True
    assert _subscribed(["roadmap.updated"], "credential.issued") is False


def test_sign_is_deterministic_hmac() -> None:
    assert _sign("secret", "body") == _sign("secret", "body")
    assert _sign("secret", "a") != _sign("secret", "b")


async def test_create_returns_secret_once(service) -> None:
    out = await service.create("u1", WebhookCreate(url="https://hooks/x", events=["*"]))
    assert isinstance(out, WebhookCreated)
    assert out.secret.startswith("whsec_")
    assert out.secret_prefix == out.secret[:12]


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


async def test_ping_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.ping("u1", "missing")


async def test_ping_delivers_and_reports_status(service, repo, http) -> None:
    repo.get = AsyncMock(return_value={"id": "w1", "url": "https://hooks/x", "secret": "s"})
    result = await service.ping("u1", "w1")
    assert result.delivered is True
    assert result.status == 200
    http.post.assert_awaited_once()


async def test_dispatch_only_to_active_and_subscribed(service, repo, http) -> None:
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "a", "url": "https://a", "secret": "s", "active": True, "events": ["roadmap.updated"]},
        {"id": "b", "url": "https://b", "secret": "s", "active": False, "events": ["*"]},   # inactive
        {"id": "c", "url": "https://c", "secret": "s", "active": True, "events": ["other"]},  # not subscribed
    ])
    await service.dispatch("u1", "roadmap.updated", {"x": 1})
    assert http.post.await_count == 1  # only webhook "a"


async def test_deliver_is_best_effort_on_network_error(service, repo, http) -> None:
    repo.get = AsyncMock(return_value={"id": "w1", "url": "https://hooks/x", "secret": "s"})
    http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    result = await service.ping("u1", "w1")  # must not raise
    assert result.delivered is False
    assert result.status is None
