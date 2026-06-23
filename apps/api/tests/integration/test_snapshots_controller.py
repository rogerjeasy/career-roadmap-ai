"""Integration tests for the Snapshots controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.snapshots.schemas import SnapshotOut
from src.domains.snapshots.service import get_snapshot_service
from src.endpoints.v1.snapshots_controller import router

pytestmark = pytest.mark.integration


class FakeSnapshotService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid, roadmap_id):
        return [SnapshotOut.from_doc(d) for d in self.store.values() if d["roadmap_id"] == roadmap_id]

    async def create(self, uid, roadmap_id, label):
        self._seq += 1
        sid = f"s{self._seq}"
        doc = {"id": sid, "roadmap_id": roadmap_id, "label": label or "Manual snapshot",
               "summary": "sum", "phase_count": 2, "auto": False}
        self.store[sid] = doc
        return SnapshotOut.from_doc(doc)

    async def restore(self, uid, snapshot_id):
        if snapshot_id not in self.store:
            raise NotFoundError("Snapshot not found.")
        return SnapshotOut.from_doc(self.store[snapshot_id])

    async def delete(self, uid, snapshot_id):
        if snapshot_id not in self.store:
            raise NotFoundError("Snapshot not found.")
        del self.store[snapshot_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeSnapshotService()
    app = make_app(
        router=router,
        overrides={get_snapshot_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_then_list_for_roadmap(client: TestClient) -> None:
    created = client.post("/roadmap-snapshots", json={"roadmapId": "rm1", "label": "v1"})
    assert created.status_code == 201
    listed = client.get("/roadmap-snapshots", params={"roadmapId": "rm1"})
    assert listed.status_code == 200
    assert listed.json()[0]["label"] == "v1"


def test_list_requires_roadmap_id(client: TestClient) -> None:
    assert client.get("/roadmap-snapshots").status_code == 422


def test_restore_flow(client: TestClient) -> None:
    sid = client.post("/roadmap-snapshots", json={"roadmapId": "rm1"}).json()["id"]
    resp = client.post(f"/roadmap-snapshots/{sid}/restore")
    assert resp.status_code == 200


def test_restore_missing_returns_404(client: TestClient) -> None:
    assert client.post("/roadmap-snapshots/nope/restore").status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    sid = client.post("/roadmap-snapshots", json={"roadmapId": "rm1"}).json()["id"]
    assert client.delete(f"/roadmap-snapshots/{sid}").status_code == 204
