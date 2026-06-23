"""Integration tests for the Push controller."""
import pytest
from fastapi.testclient import TestClient

from src.domains.push.schemas import PushConfig, PushSendResult, PushSubscriptionIn
from src.domains.push.service import get_push_service
from src.endpoints.v1.push_controller import router

pytestmark = pytest.mark.integration


class FakePushService:
    def __init__(self) -> None:
        self.subs: list = []

    def config(self):
        return PushConfig(enabled=False, public_key=None)

    async def subscribe(self, uid, payload: PushSubscriptionIn):
        self.subs.append(payload.endpoint)

    async def unsubscribe(self, uid, endpoint):
        self.subs = [s for s in self.subs if s != endpoint]

    async def send_test(self, uid):
        return PushSendResult(sent=0, failed=0, enabled=False, detail="not configured")


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakePushService()
    app = make_app(
        router=router,
        overrides={get_push_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_config_endpoint(client: TestClient) -> None:
    resp = client.get("/push/config")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_subscribe_and_unsubscribe(client: TestClient) -> None:
    sub = {"endpoint": "https://push/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/push/subscribe", json=sub).status_code == 204
    assert client.post("/push/unsubscribe", json={"endpoint": "https://push/abc"}).status_code == 204


def test_test_send_returns_result(client: TestClient) -> None:
    resp = client.post("/push/test")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_subscribe_rejects_missing_keys(client: TestClient) -> None:
    assert client.post("/push/subscribe", json={"endpoint": "https://x"}).status_code == 422
