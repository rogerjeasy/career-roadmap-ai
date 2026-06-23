"""Integration tests for the Feedback controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut
from src.domains.feedback.service import get_feedback_service
from src.endpoints.v1.feedback_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeFeedbackService:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self._seq = 0

    async def list(self, uid: str, *, limit: int = 50) -> list[FeedbackOut]:
        return [FeedbackOut.from_doc(d) for d in self.items][:limit]

    async def create(self, uid: str, body: FeedbackCreate) -> FeedbackOut:
        self._seq += 1
        doc = {"id": f"f{self._seq}", "created_at": NOW, **body.model_dump()}
        self.items.append(doc)
        return FeedbackOut.from_doc(doc)


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeFeedbackService()
    app = make_app(
        router=router,
        overrides={get_feedback_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_then_list(client: TestClient) -> None:
    created = client.post("/feedback", json={"subject": "Bug", "message": "It broke", "category": "bug"})
    assert created.status_code == 201
    body = created.json()
    assert body["category"] == "bug"
    assert "createdAt" in body

    listed = client.get("/feedback")
    assert listed.status_code == 200
    assert listed.json()[0]["subject"] == "Bug"


def test_create_rejects_rating_out_of_range(client: TestClient) -> None:
    resp = client.post("/feedback", json={"subject": "s", "message": "m", "rating": 9})
    assert resp.status_code == 422


def test_list_limit_validated(client: TestClient) -> None:
    resp = client.get("/feedback", params={"limit": 500})  # le=100
    assert resp.status_code == 422
