"""Integration tests for the Monthly Plan controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.monthly_plan.schemas import MonthlyPlanOut, MonthlyPlanSummaryOut, MonthlyPlanUpsert
from src.domains.monthly_plan.service import get_monthly_plan_service
from src.endpoints.v1.monthly_plan_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeMonthlyPlanService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def list(self, uid):
        docs = sorted(self.store.values(), key=lambda d: d["month_id"])
        return [MonthlyPlanSummaryOut.from_doc(d) for d in docs]

    async def get(self, uid, month_id):
        if month_id not in self.store:
            raise NotFoundError("not found")
        return MonthlyPlanOut.from_doc(self.store[month_id])

    async def upsert(self, uid, payload: MonthlyPlanUpsert):
        self.store[payload.month_id] = {"id": payload.month_id, "created_at": NOW, **payload.model_dump()}
        return MonthlyPlanOut.from_doc(self.store[payload.month_id])

    async def delete(self, uid, month_id):
        if month_id not in self.store:
            raise NotFoundError("not found")
        del self.store[month_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeMonthlyPlanService()
    app = make_app(
        router=router,
        overrides={get_monthly_plan_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_upsert_then_get(client: TestClient) -> None:
    up = client.put("/monthly-plans", json={"monthId": "2026-06", "month": "June 2026", "theme": "Ship"})
    assert up.status_code == 200
    got = client.get("/monthly-plans/2026-06")
    assert got.status_code == 200
    assert got.json()["theme"] == "Ship"


def test_list_is_sorted(client: TestClient) -> None:
    client.put("/monthly-plans", json={"monthId": "2026-07", "month": "Jul"})
    client.put("/monthly-plans", json={"monthId": "2026-05", "month": "May"})
    months = [p["monthId"] for p in client.get("/monthly-plans").json()]
    assert months == ["2026-05", "2026-07"]


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/monthly-plans/2099-01").status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    client.put("/monthly-plans", json={"monthId": "2026-06", "month": "June"})
    assert client.delete("/monthly-plans/2026-06").status_code == 204


def test_upsert_rejects_blank_month(client: TestClient) -> None:
    assert client.put("/monthly-plans", json={"monthId": "2026-06", "month": ""}).status_code == 422
