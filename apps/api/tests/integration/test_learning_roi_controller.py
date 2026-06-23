"""Integration tests for the Learning ROI controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.learning_roi.schemas import (
    LearningItemCreate,
    LearningItemOut,
    LearningItemUpdate,
    LearningRoiSummary,
)
from src.domains.learning_roi.service import get_learning_roi_service
from src.endpoints.v1.learning_roi_controller import router

pytestmark = pytest.mark.integration


class FakeLearningRoiService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list_ranked(self, uid):
        return [LearningItemOut.from_doc(d) for d in self.store.values()]

    async def summary(self, uid):
        return LearningRoiSummary(
            total_items=len(self.store), total_cost=0.0, total_hours=0.0,
            average_roi=0, has_market_signals=False,
        )

    async def create(self, uid, payload: LearningItemCreate):
        self._seq += 1
        iid = f"i{self._seq}"
        doc = {"id": iid, **payload.model_dump()}
        self.store[iid] = doc
        return LearningItemOut.from_doc(doc)

    async def update(self, uid, item_id, payload: LearningItemUpdate):
        if item_id not in self.store:
            raise NotFoundError("Learning item not found.")
        self.store[item_id].update(payload.to_patch())
        return LearningItemOut.from_doc(self.store[item_id])

    async def delete(self, uid, item_id):
        if item_id not in self.store:
            raise NotFoundError("Learning item not found.")
        del self.store[item_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeLearningRoiService()
    app = make_app(
        router=router,
        overrides={get_learning_roi_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_list_summary(client: TestClient) -> None:
    created = client.post("/learning", json={"title": "SQL", "type": "course", "cost": 100})
    assert created.status_code == 201
    assert client.get("/learning").json()[0]["title"] == "SQL"
    assert client.get("/learning/summary").json()["totalItems"] == 1


def test_update_item(client: TestClient) -> None:
    iid = client.post("/learning", json={"title": "X"}).json()["id"]
    resp = client.patch(f"/learning/{iid}", json={"status": "completed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_update_missing_returns_404(client: TestClient) -> None:
    assert client.patch("/learning/nope", json={"title": "x"}).status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    iid = client.post("/learning", json={"title": "X"}).json()["id"]
    assert client.delete(f"/learning/{iid}").status_code == 204


def test_create_rejects_blank_title(client: TestClient) -> None:
    assert client.post("/learning", json={"title": ""}).status_code == 422
