"""Integration tests for the Contact controller (public, unauthenticated)."""
import pytest
from fastapi.testclient import TestClient

from src.domains.contact.schemas import ContactRequestAck
from src.domains.contact.service import get_contact_service
from src.endpoints.v1.contact_controller import router

pytestmark = pytest.mark.integration


class FakeContactService:
    def __init__(self) -> None:
        self.submitted: list = []

    async def submit(self, payload):
        self.submitted.append(payload)
        return ContactRequestAck()


@pytest.fixture
def service() -> FakeContactService:
    return FakeContactService()


@pytest.fixture
def client(make_app, service: FakeContactService) -> TestClient:
    app = make_app(
        router=router,
        overrides={get_contact_service: lambda: service},
        case_conversion=True,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_submit_returns_201_ack(client: TestClient, service: FakeContactService) -> None:
    resp = client.post(
        "/contact",
        json={"name": "Ada", "email": "ada@example.com", "message": "Hello"},
    )
    assert resp.status_code == 201
    assert resp.json()["received"] is True
    assert len(service.submitted) == 1


def test_submit_rejects_invalid_email(client: TestClient) -> None:
    resp = client.post("/contact", json={"name": "Ada", "email": "nope", "message": "x"})
    assert resp.status_code == 422


def test_submit_rejects_blank_message(client: TestClient) -> None:
    resp = client.post("/contact", json={"name": "Ada", "email": "a@b.com", "message": ""})
    assert resp.status_code == 422


def test_submit_rejects_unknown_topic(client: TestClient) -> None:
    resp = client.post(
        "/contact",
        json={"name": "Ada", "email": "a@b.com", "message": "hi", "topic": "spam"},
    )
    assert resp.status_code == 422
