"""Integration tests for the Webhooks controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.webhooks.schemas import WebhookCreate, WebhookCreated, WebhookOut, WebhookPingResult
from src.domains.webhooks.service import get_webhook_service
from src.endpoints.v1.webhooks_controller import router

pytestmark = pytest.mark.integration


class FakeWebhookService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid):
        return [WebhookOut.from_doc(d) for d in self.store.values()]

    async def create(self, uid, payload: WebhookCreate):
        self._seq += 1
        wid = f"w{self._seq}"
        secret = "whsec_secretvalue"
        self.store[wid] = {"id": wid, "url": str(payload.url), "events": payload.events, "active": True, "secret": secret}
        out = WebhookOut.from_doc(self.store[wid])
        return WebhookCreated(**out.model_dump(), secret=secret)

    async def ping(self, uid, webhook_id):
        if webhook_id not in self.store:
            raise NotFoundError("Webhook not found.")
        return WebhookPingResult(delivered=True, status=200, detail="")

    async def delete(self, uid, webhook_id):
        if webhook_id not in self.store:
            raise NotFoundError("Webhook not found.")
        del self.store[webhook_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeWebhookService()
    app = make_app(
        router=router,
        overrides={get_webhook_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_returns_full_secret_once(client: TestClient) -> None:
    resp = client.post("/webhooks", json={"url": "https://hooks.example.com/x", "events": ["*"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["secret"].startswith("whsec_")
    assert body["secretPrefix"] == body["secret"][:12]


def test_list_omits_full_secret(client: TestClient) -> None:
    client.post("/webhooks", json={"url": "https://hooks.example.com/x"})
    item = client.get("/webhooks").json()[0]
    assert "secret" not in item  # only secretPrefix is exposed
    assert "secretPrefix" in item


def test_ping_and_delete(client: TestClient) -> None:
    wid = client.post("/webhooks", json={"url": "https://hooks.example.com/x"}).json()["id"]
    assert client.post(f"/webhooks/{wid}/ping").json()["delivered"] is True
    assert client.delete(f"/webhooks/{wid}").status_code == 204


def test_ping_missing_returns_404(client: TestClient) -> None:
    assert client.post("/webhooks/nope/ping").status_code == 404


def test_create_rejects_invalid_url(client: TestClient) -> None:
    assert client.post("/webhooks", json={"url": "not-a-url"}).status_code == 422
