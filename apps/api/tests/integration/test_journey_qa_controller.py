"""Integration tests for the Ask-My-Journey controller."""
import pytest
from fastapi.testclient import TestClient

from src.domains.journey_qa.schemas import AskInput, AskReply
from src.domains.journey_qa.service import get_journey_qa_service
from src.endpoints.v1.journey_qa_controller import router

pytestmark = pytest.mark.integration


class FakeJourneyQaService:
    async def ask(self, uid: str, payload: AskInput) -> AskReply:
        return AskReply(answer=f"echo: {payload.question}", sources=["applications"], suggestions=[])


@pytest.fixture
def client(make_app, user) -> TestClient:
    app = make_app(
        router=router,
        overrides={get_journey_qa_service: lambda: FakeJourneyQaService()},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_ask_returns_reply(client: TestClient) -> None:
    resp = client.post("/journey/ask", json={"question": "How am I doing?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"].startswith("echo:")
    assert body["sources"] == ["applications"]


def test_ask_rejects_empty_question(client: TestClient) -> None:
    assert client.post("/journey/ask", json={"question": ""}).status_code == 422


def test_ask_rejects_oversized_history(client: TestClient) -> None:
    history = [{"role": "user", "content": "hi"}] * 21  # max_length=20
    resp = client.post("/journey/ask", json={"question": "q", "history": history})
    assert resp.status_code == 422
