"""Integration tests for the Storytelling controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.storytelling.schemas import StoryDraftOut, StoryGenerateInput
from src.domains.storytelling.service import get_storytelling_service
from src.endpoints.v1.storytelling_controller import router

pytestmark = pytest.mark.integration


class FakeStorytellingService:
    def __init__(self) -> None:
        self.store: dict[str, StoryDraftOut] = {}
        self._seq = 0

    async def generate(self, uid, payload: StoryGenerateInput):
        if not payload.evidence_ids:
            raise ValidationError("Select at least one evidence item.")
        self._seq += 1
        did = f"d{self._seq}"
        draft = StoryDraftOut(
            id=did, format=payload.format, tone=payload.tone,
            target_role=payload.target_role, target_company=payload.target_company,
            title="T", content="C", highlights=[], tips=[], evidence_titles=["E1"],
        )
        self.store[did] = draft
        return draft

    async def list_drafts(self, uid):
        return list(self.store.values())

    async def get_draft(self, uid, draft_id):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        return self.store[draft_id]

    async def delete_draft(self, uid, draft_id):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        del self.store[draft_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeStorytellingService()
    app = make_app(
        router=router,
        overrides={get_storytelling_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_generate_then_get(client: TestClient) -> None:
    created = client.post("/storytelling/generate", json={"format": "cover_letter", "evidenceIds": ["e1"]})
    assert created.status_code == 201
    did = created.json()["id"]
    got = client.get(f"/storytelling/drafts/{did}")
    assert got.status_code == 200
    assert got.json()["format"] == "cover_letter"


def test_generate_without_evidence_returns_422(client: TestClient) -> None:
    resp = client.post("/storytelling/generate", json={"evidenceIds": []})
    assert resp.status_code == 422
    assert resp.json()["errorCode"] == "validation_error"


def test_generate_rejects_unknown_format(client: TestClient) -> None:
    resp = client.post("/storytelling/generate", json={"format": "tweet", "evidenceIds": ["e1"]})
    assert resp.status_code == 422  # request schema validation


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/storytelling/drafts/nope").status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    did = client.post("/storytelling/generate", json={"evidenceIds": ["e1"]}).json()["id"]
    assert client.delete(f"/storytelling/drafts/{did}").status_code == 204
