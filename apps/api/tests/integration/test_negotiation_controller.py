"""Integration tests for the Negotiation controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.negotiation.schemas import (
    OfferAnalysisOut,
    OfferInput,
    RoleplayInput,
    RoleplayReply,
)
from src.domains.negotiation.service import get_negotiation_service
from src.endpoints.v1.negotiation_controller import router

pytestmark = pytest.mark.integration


def _analysis(oid: str, offer: OfferInput) -> OfferAnalysisOut:
    return OfferAnalysisOut(
        id=oid, offer=offer, assessment="ok", competitiveness="at",
        benchmark_low=1, benchmark_high=2, benchmark_currency="USD",
        counter_base=2, counter_rationale="r", talking_points=[], risks=[],
        assumptions=[], confidence=0.5,
    )


class FakeNegotiationService:
    def __init__(self) -> None:
        self.store: dict[str, OfferAnalysisOut] = {}
        self._seq = 0

    async def analyze(self, uid, offer: OfferInput):
        self._seq += 1
        oid = f"o{self._seq}"
        a = _analysis(oid, offer)
        self.store[oid] = a
        return a

    async def list(self, uid):
        return list(self.store.values())

    async def get(self, uid, offer_id):
        if offer_id not in self.store:
            raise NotFoundError("Offer analysis not found.")
        return self.store[offer_id]

    async def delete(self, uid, offer_id):
        if offer_id not in self.store:
            raise NotFoundError("Offer analysis not found.")
        del self.store[offer_id]

    async def roleplay(self, uid, payload: RoleplayInput):
        return RoleplayReply(reply="r", coaching="c", tip="t")


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeNegotiationService()
    app = make_app(
        router=router,
        overrides={get_negotiation_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_analyze_then_get(client: TestClient) -> None:
    created = client.post("/negotiation/analyze", json={"role": "PM", "baseSalary": 150000})
    assert created.status_code == 201
    oid = created.json()["id"]
    got = client.get(f"/negotiation/offers/{oid}")
    assert got.status_code == 200
    assert got.json()["competitiveness"] == "at"


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/negotiation/offers/nope").status_code == 404


def test_delete_flow(client: TestClient) -> None:
    oid = client.post("/negotiation/analyze", json={"role": "PM"}).json()["id"]
    assert client.delete(f"/negotiation/offers/{oid}").status_code == 204


def test_analyze_rejects_blank_role(client: TestClient) -> None:
    assert client.post("/negotiation/analyze", json={"role": ""}).status_code == 422


def test_roleplay_returns_reply(client: TestClient) -> None:
    resp = client.post(
        "/negotiation/roleplay",
        json={"offer": {"role": "PM"}, "message": "I want more"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "r"


def test_roleplay_rejects_blank_message(client: TestClient) -> None:
    resp = client.post("/negotiation/roleplay", json={"offer": {"role": "PM"}, "message": ""})
    assert resp.status_code == 422
