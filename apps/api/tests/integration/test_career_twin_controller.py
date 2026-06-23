"""Integration tests for the Career Twin controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.career_twin.schemas import DailyCheckinOut, TwinPersonaOut, TwinPersonaUpsert
from src.domains.career_twin.service import get_career_twin_service
from src.endpoints.v1.career_twin_controller import router

pytestmark = pytest.mark.integration


class FakeCareerTwinService:
    def __init__(self) -> None:
        self.persona = TwinPersonaOut(name="Your Career Twin", voice="supportive", focus="", check_in_enabled=True)
        self.checkin: DailyCheckinOut | None = None

    async def get_persona(self, uid):
        return self.persona

    async def upsert_persona(self, uid, payload: TwinPersonaUpsert):
        self.persona = TwinPersonaOut(name=payload.name, voice=payload.voice, focus=payload.focus, check_in_enabled=payload.check_in_enabled)
        return self.persona

    async def today(self, uid):
        self.checkin = DailyCheckinOut(
            id="ck1", date="2026-06-23", greeting="Hi", prompt="What today?",
            focus_suggestion="", user_reply="", twin_response="", status="open",
        )
        return self.checkin

    async def reply(self, uid, checkin_id, reply, mood):
        if self.checkin is None or checkin_id != self.checkin.id:
            raise NotFoundError("Check-in not found.")
        self.checkin = self.checkin.model_copy(update={"user_reply": reply, "twin_response": "Keep going", "status": "answered", "mood": mood})
        return self.checkin

    async def history(self, uid, limit=60):
        return [self.checkin] if self.checkin else []


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeCareerTwinService()
    app = make_app(
        router=router,
        overrides={get_career_twin_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_persona_get_and_update(client: TestClient) -> None:
    assert client.get("/career-twin/persona").json()["name"] == "Your Career Twin"
    up = client.put("/career-twin/persona", json={"name": "Coach", "voice": "direct"})
    assert up.status_code == 200
    assert up.json()["voice"] == "direct"


def test_today_then_reply(client: TestClient) -> None:
    today = client.get("/career-twin/today")
    assert today.status_code == 200
    cid = today.json()["id"]
    replied = client.post(f"/career-twin/{cid}/reply", json={"reply": "I shipped a feature", "mood": 4})
    assert replied.status_code == 200
    assert replied.json()["status"] == "answered"
    assert replied.json()["twinResponse"] == "Keep going"


def test_reply_rejects_blank(client: TestClient) -> None:
    client.get("/career-twin/today")
    assert client.post("/career-twin/ck1/reply", json={"reply": ""}).status_code == 422


def test_reply_rejects_bad_mood(client: TestClient) -> None:
    client.get("/career-twin/today")
    assert client.post("/career-twin/ck1/reply", json={"reply": "x", "mood": 9}).status_code == 422


def test_history(client: TestClient) -> None:
    client.get("/career-twin/today")
    assert client.get("/career-twin/history").status_code == 200
