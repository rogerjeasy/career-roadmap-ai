"""Integration tests for the Privacy controller."""
import pytest
from fastapi.testclient import TestClient

from src.domains.privacy.service import get_privacy_service
from src.endpoints.v1.privacy_controller import router

pytestmark = pytest.mark.integration


class FakePrivacyService:
    def __init__(self) -> None:
        self.deleted = False

    async def export(self, uid):
        return {"user_id": uid, "generated_at": "2026-06-23T00:00:00Z", "collections": {"books": [{"id": "b1"}]}}

    async def purge_data(self, uid):
        return 7

    async def delete_account(self, uid):
        self.deleted = True


@pytest.fixture
def service() -> FakePrivacyService:
    return FakePrivacyService()


@pytest.fixture
def client(make_app, user, service: FakePrivacyService) -> TestClient:
    app = make_app(
        router=router,
        overrides={get_privacy_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_export_returns_bundle(client: TestClient) -> None:
    resp = client.get("/privacy/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["userId"] == "user-123"  # snake→camel by middleware
    assert "generatedAt" in body
    assert body["collections"]["books"][0]["id"] == "b1"


def test_purge_returns_count(client: TestClient) -> None:
    resp = client.post("/privacy/purge")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 7


def test_delete_account_returns_204(client: TestClient, service: FakePrivacyService) -> None:
    resp = client.delete("/privacy/account")
    assert resp.status_code == 204
    assert service.deleted is True
