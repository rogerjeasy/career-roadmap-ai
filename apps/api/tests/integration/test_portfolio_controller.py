"""Integration tests for the Portfolio controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.portfolio.schemas import PortfolioItemCreate, PortfolioItemOut, PortfolioItemUpdate
from src.domains.portfolio.service import get_portfolio_service
from src.endpoints.v1.portfolio_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakePortfolioService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid, limit=100):
        return [PortfolioItemOut.from_doc(d) for d in self.store.values()][:limit]

    async def get(self, uid, item_id):
        if item_id not in self.store:
            raise NotFoundError("not found")
        return PortfolioItemOut.from_doc(self.store[item_id])

    async def create(self, uid, payload: PortfolioItemCreate):
        self._seq += 1
        pid = f"p{self._seq}"
        self.store[pid] = {"id": pid, "created_at": NOW, **payload.model_dump()}
        return PortfolioItemOut.from_doc(self.store[pid])

    async def update(self, uid, item_id, payload: PortfolioItemUpdate):
        if item_id not in self.store:
            raise NotFoundError("not found")
        self.store[item_id].update(payload.to_patch())
        return PortfolioItemOut.from_doc(self.store[item_id])

    async def delete(self, uid, item_id):
        if item_id not in self.store:
            raise NotFoundError("not found")
        del self.store[item_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakePortfolioService()
    app = make_app(
        router=router,
        overrides={get_portfolio_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_crud_flow(client: TestClient) -> None:
    created = client.post("/portfolio", json={"title": "My App", "repoUrl": "https://gh/x"})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert client.get(f"/portfolio/{pid}").json()["repoUrl"] == "https://gh/x"
    upd = client.patch(f"/portfolio/{pid}", json={"status": "archived"})
    assert upd.json()["status"] == "archived"
    assert client.delete(f"/portfolio/{pid}").status_code == 204


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/portfolio/nope").status_code == 404


def test_create_rejects_blank_title(client: TestClient) -> None:
    assert client.post("/portfolio", json={"title": ""}).status_code == 422
