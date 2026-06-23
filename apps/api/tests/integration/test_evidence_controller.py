"""Integration tests for the Evidence controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.evidence.schemas import EvidenceCreate, EvidenceOut, EvidenceUpdate
from src.domains.evidence.service import get_evidence_service
from src.endpoints.v1.evidence_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeEvidenceService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid, limit=100):
        return [EvidenceOut.from_doc(d) for d in self.store.values()][:limit]

    async def get(self, uid, evidence_id):
        if evidence_id not in self.store:
            raise NotFoundError("not found")
        return EvidenceOut.from_doc(self.store[evidence_id])

    async def create(self, uid, payload: EvidenceCreate):
        self._seq += 1
        eid = f"e{self._seq}"
        self.store[eid] = {"id": eid, "created_at": NOW, **payload.model_dump()}
        return EvidenceOut.from_doc(self.store[eid])

    async def update(self, uid, evidence_id, payload: EvidenceUpdate):
        if evidence_id not in self.store:
            raise NotFoundError("not found")
        self.store[evidence_id].update(payload.to_patch())
        return EvidenceOut.from_doc(self.store[evidence_id])

    async def delete(self, uid, evidence_id):
        if evidence_id not in self.store:
            raise NotFoundError("not found")
        del self.store[evidence_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeEvidenceService()
    app = make_app(
        router=router,
        overrides={get_evidence_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_crud_flow(client: TestClient) -> None:
    created = client.post("/evidence", json={"title": "Shipped X", "type": "project"})
    assert created.status_code == 201
    eid = created.json()["id"]
    assert client.get(f"/evidence/{eid}").json()["title"] == "Shipped X"
    upd = client.patch(f"/evidence/{eid}", json={"title": "Shipped Y"})
    assert upd.json()["title"] == "Shipped Y"
    assert client.delete(f"/evidence/{eid}").status_code == 204


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/evidence/nope").status_code == 404


def test_create_rejects_blank_title(client: TestClient) -> None:
    assert client.post("/evidence", json={"title": ""}).status_code == 422


def test_list_limit_validated(client: TestClient) -> None:
    assert client.get("/evidence", params={"limit": 999}).status_code == 422
