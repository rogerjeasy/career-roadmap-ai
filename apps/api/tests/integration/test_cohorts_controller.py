"""Integration tests for the Cohorts controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import AuthorizationError, NotFoundError
from src.domains.cohorts.schemas import (
    CheckinCreate,
    CheckinOut,
    CohortCreate,
    CohortDashboard,
    CohortOut,
)
from src.domains.cohorts.service import get_cohort_service
from src.endpoints.v1.cohorts_controller import router

pytestmark = pytest.mark.integration


def _cohort(cid: str, uid: str, **over) -> CohortOut:
    base = dict(
        id=cid, name="Hunt", focus="PM", description="", capacity=6, cadence="weekly",
        status="open", created_by=uid, members=[], member_count=1, is_member=True, is_owner=True,
    )
    base.update(over)
    return CohortOut(**base)


class FakeCohortService:
    def __init__(self) -> None:
        self.store: dict[str, CohortOut] = {}
        self._seq = 0

    async def list_mine(self, uid):
        return list(self.store.values())

    async def discover(self, uid):
        return []

    async def create(self, uid, name, payload: CohortCreate):
        self._seq += 1
        cid = f"c{self._seq}"
        c = _cohort(cid, uid, name=payload.name, focus=payload.focus)
        self.store[cid] = c
        return c

    async def dashboard(self, uid, cohort_id):
        if cohort_id not in self.store:
            raise NotFoundError("Cohort not found.")
        return CohortDashboard(cohort=self.store[cohort_id], checkins=[])

    async def join(self, uid, name, cohort_id):
        if cohort_id not in self.store:
            raise NotFoundError("Cohort not found.")
        return self.store[cohort_id]

    async def leave(self, uid, cohort_id):
        if cohort_id not in self.store:
            raise NotFoundError("Cohort not found.")

    async def post_checkin(self, uid, name, cohort_id, payload: CheckinCreate):
        if cohort_id not in self.store:
            raise AuthorizationError("Not a member.")
        return CheckinOut(id="ck1", cohort_id=cohort_id, user_id=uid, user_name=name, done=payload.done, next="", blockers="")


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeCohortService()
    app = make_app(
        router=router,
        overrides={get_cohort_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_then_list_and_dashboard(client: TestClient) -> None:
    created = client.post("/cohorts", json={"name": "Hunt", "focus": "PM roles"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert client.get("/cohorts").status_code == 200
    dash = client.get(f"/cohorts/{cid}")
    assert dash.status_code == 200
    assert dash.json()["cohort"]["id"] == cid


def test_discover_endpoint(client: TestClient) -> None:
    assert client.get("/cohorts/discover").json() == []


def test_join_and_checkin_and_leave(client: TestClient) -> None:
    cid = client.post("/cohorts", json={"name": "H", "focus": "F"}).json()["id"]
    assert client.post(f"/cohorts/{cid}/join").status_code == 200
    ck = client.post(f"/cohorts/{cid}/checkins", json={"done": "shipped"})
    assert ck.status_code == 201
    assert client.post(f"/cohorts/{cid}/leave").status_code == 204


def test_dashboard_missing_returns_404(client: TestClient) -> None:
    assert client.get("/cohorts/nope").status_code == 404


def test_create_rejects_capacity_below_minimum(client: TestClient) -> None:
    assert client.post("/cohorts", json={"name": "H", "focus": "F", "capacity": 1}).status_code == 422
