"""Integration tests for the Wellness controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.wellness.schemas import (
    WellnessCheckinCreate,
    WellnessCheckinOut,
    WellnessStatus,
)
from src.domains.wellness.service import get_wellness_service
from src.endpoints.v1.wellness_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeWellnessService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def status(self, uid: str) -> WellnessStatus:
        return WellnessStatus(
            risk_score=30,
            risk_level="low",
            trend="stable",
            drivers=[],
            recommendation="Keep it up",
            recovery_suggested=False,
            sample_size=len(self.store),
        )

    async def list_checkins(self, uid: str, limit: int = 60) -> list[WellnessCheckinOut]:
        return [WellnessCheckinOut.from_doc(d) for d in self.store.values()]

    async def log_checkin(self, uid: str, payload: WellnessCheckinCreate) -> WellnessCheckinOut:
        self._seq += 1
        cid = f"w{self._seq}"
        doc = {"id": cid, "created_at": NOW, **payload.model_dump()}
        self.store[cid] = doc
        return WellnessCheckinOut.from_doc(doc)

    async def delete_checkin(self, uid: str, checkin_id: str) -> None:
        if checkin_id not in self.store:
            raise NotFoundError("Check-in not found.")
        del self.store[checkin_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeWellnessService()
    app = make_app(
        router=router,
        overrides={get_wellness_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_status_endpoint(client: TestClient) -> None:
    resp = client.get("/wellness/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["riskLevel"] == "low"
    assert body["recoverySuggested"] is False


def test_checkin_create_list_delete_flow(client: TestClient) -> None:
    created = client.post(
        "/wellness/checkins",
        json={"energy": 4, "stress": 2, "motivation": 5},
    )
    assert created.status_code == 201
    cid = created.json()["id"]

    listed = client.get("/wellness/checkins")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = client.delete(f"/wellness/checkins/{cid}")
    assert deleted.status_code == 204


def test_delete_missing_returns_404(client: TestClient) -> None:
    resp = client.delete("/wellness/checkins/nope")
    assert resp.status_code == 404


def test_create_rejects_out_of_range_energy(client: TestClient) -> None:
    resp = client.post("/wellness/checkins", json={"energy": 9, "stress": 2, "motivation": 5})
    assert resp.status_code == 422
