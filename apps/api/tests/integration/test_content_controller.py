"""Integration tests for the Content controller."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.content.schemas import ContentDraftOut, ContentGenerateInput
from src.domains.content.service import get_content_service
from src.domains.webhooks.service import get_webhook_service
from src.endpoints.v1.content_controller import router

pytestmark = pytest.mark.integration


class FakeContentService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0
        self.linkedin = False

    def _out(self, d) -> ContentDraftOut:
        return ContentDraftOut.from_doc(d)

    async def list(self, uid):
        return [self._out(d) for d in self.store.values()]

    async def generate(self, uid, payload: ContentGenerateInput):
        self._seq += 1
        did = f"d{self._seq}"
        self.store[did] = {"id": did, "kind": payload.kind, "tone": payload.tone, "content": "Post body", "status": "draft", "hashtags": []}
        return self._out(self.store[did])

    async def get(self, uid, draft_id):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        return self._out(self.store[draft_id])

    async def set_status(self, uid, draft_id, status):
        d = self.store.get(draft_id)
        if d is None:
            raise NotFoundError("Draft not found.")
        if status == "published" and not self.linkedin:
            raise ValidationError("Connect LinkedIn first.")
        d["status"] = status
        return self._out(d)

    async def delete(self, uid, draft_id):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        del self.store[draft_id]


@pytest.fixture
def service() -> FakeContentService:
    return FakeContentService()


@pytest.fixture
def client(make_app, user, service: FakeContentService) -> TestClient:
    webhooks = MagicMock()
    webhooks.dispatch = AsyncMock()
    app = make_app(
        router=router,
        overrides={
            get_content_service: lambda: service,
            get_webhook_service: lambda: webhooks,
        },
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_generate_then_get(client: TestClient) -> None:
    did = client.post("/content", json={"kind": "linkedin_post", "milestone": "Shipped"}).json()["id"]
    got = client.get(f"/content/{did}")
    assert got.status_code == 200
    assert got.json()["status"] == "draft"


def test_publish_blocked_without_linkedin(client: TestClient) -> None:
    did = client.post("/content", json={"kind": "linkedin_post"}).json()["id"]
    resp = client.patch(f"/content/{did}/status", json={"status": "published"})
    assert resp.status_code == 422


def test_publish_allowed_when_connected(client: TestClient, service: FakeContentService) -> None:
    service.linkedin = True
    did = client.post("/content", json={"kind": "linkedin_post"}).json()["id"]
    resp = client.patch(f"/content/{did}/status", json={"status": "published"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_delete_returns_204(client: TestClient) -> None:
    did = client.post("/content", json={"kind": "linkedin_post"}).json()["id"]
    assert client.delete(f"/content/{did}").status_code == 204


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/content/nope").status_code == 404
