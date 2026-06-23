"""Integration tests for the Discovery controller."""
import pytest
from fastapi.testclient import TestClient

from src.domains.discovery.schemas import CareerPathOption, DiscoveryResult
from src.domains.discovery.service import get_discovery_service
from src.endpoints.v1.discovery_controller import router

pytestmark = pytest.mark.integration


class FakeDiscoveryService:
    def __init__(self) -> None:
        self.result = DiscoveryResult.empty()

    async def get(self, uid):
        return self.result

    async def generate(self, uid):
        self.result = DiscoveryResult(
            paths=[CareerPathOption(title="Data Scientist", fit_score=80)],
            based_on="your CV", confidence=0.7, has_data=True,
        )
        return self.result


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeDiscoveryService()
    app = make_app(
        router=router,
        overrides={get_discovery_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_get_empty_before_generate(client: TestClient) -> None:
    resp = client.get("/discovery")
    assert resp.status_code == 200
    assert resp.json()["hasData"] is False


def test_generate_then_get(client: TestClient) -> None:
    gen = client.post("/discovery/generate")
    assert gen.status_code == 200
    body = gen.json()
    assert body["hasData"] is True
    assert body["paths"][0]["fitScore"] == 80
    # subsequent GET returns the cached result
    assert client.get("/discovery").json()["hasData"] is True
