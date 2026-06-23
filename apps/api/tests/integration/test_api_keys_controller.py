"""Integration tests for the API Keys controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.api_keys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from src.domains.api_keys.service import get_api_key_service
from src.endpoints.v1.api_keys_controller import router

pytestmark = pytest.mark.integration


class FakeApiKeyService:
    def __init__(self) -> None:
        self.keys: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid):
        return [ApiKeyOut.from_doc(d) for d in self.keys.values()]

    async def create(self, uid, payload: ApiKeyCreate):
        self._seq += 1
        kid = f"k{self._seq}"
        doc = {"id": kid, "name": payload.name, "prefix": "cra_live_ab", "last4": "wxyz", "revoked": False}
        self.keys[kid] = doc
        return ApiKeyCreated(**ApiKeyOut.from_doc(doc).model_dump(), key="cra_live_secret_value")

    async def revoke(self, uid, key_id):
        if key_id not in self.keys:
            raise NotFoundError("API key not found.")
        self.keys[key_id]["revoked"] = True
        return ApiKeyOut.from_doc(self.keys[key_id])

    async def delete(self, uid, key_id):
        if key_id not in self.keys:
            raise NotFoundError("API key not found.")
        del self.keys[key_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeApiKeyService()
    app = make_app(
        router=router,
        overrides={get_api_key_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_returns_secret_once(client: TestClient) -> None:
    resp = client.post("/api-keys", json={"name": "CI"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"].startswith("cra_live_")
    assert body["last4"] == "wxyz"


def test_list_omits_secret(client: TestClient) -> None:
    client.post("/api-keys", json={"name": "CI"})
    resp = client.get("/api-keys")
    assert resp.status_code == 200
    assert "key" not in resp.json()[0]  # secret never returned on list


def test_revoke_flow(client: TestClient) -> None:
    kid = client.post("/api-keys", json={"name": "CI"}).json()["id"]
    resp = client.post(f"/api-keys/{kid}/revoke")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_revoke_missing_returns_404(client: TestClient) -> None:
    assert client.post("/api-keys/missing/revoke").status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    kid = client.post("/api-keys", json={"name": "CI"}).json()["id"]
    assert client.delete(f"/api-keys/{kid}").status_code == 204


def test_create_rejects_blank_name(client: TestClient) -> None:
    assert client.post("/api-keys", json={"name": ""}).status_code == 422
