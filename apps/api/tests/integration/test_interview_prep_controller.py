"""Integration tests for the Interview Prep controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.interview_prep.schemas import (
    InterviewQuestion,
    QuestionRequest,
    QuestionSet,
    SessionCreate,
    SessionOut,
    TurnInput,
    TurnReply,
)
from src.domains.interview_prep.service import get_interview_prep_service
from src.endpoints.v1.interview_prep_controller import router

pytestmark = pytest.mark.integration


class FakeInterviewPrepService:
    def __init__(self) -> None:
        self.store: dict[str, SessionOut] = {}
        self._seq = 0

    async def generate_questions(self, uid, req: QuestionRequest):
        return QuestionSet(
            role=req.role, interview_type=req.interview_type,
            questions=[InterviewQuestion(question="Q1", category="behavioral")],
        )

    async def turn(self, uid, payload: TurnInput):
        return TurnReply(feedback="f", score=75, strengths=[], improvements=[], next_question="next", done=False)

    async def list_sessions(self, uid):
        return list(self.store.values())

    async def save_session(self, uid, payload: SessionCreate):
        self._seq += 1
        sid = f"s{self._seq}"
        s = SessionOut(
            id=sid, role=payload.role, company=payload.company, interview_type=payload.interview_type,
            overall_score=payload.overall_score, transcript=payload.transcript, notes=payload.notes,
        )
        self.store[sid] = s
        return s

    async def delete_session(self, uid, session_id):
        if session_id not in self.store:
            raise NotFoundError("Interview session not found.")
        del self.store[session_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeInterviewPrepService()
    app = make_app(
        router=router,
        overrides={get_interview_prep_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_generate_questions(client: TestClient) -> None:
    resp = client.post("/interview/questions", json={"role": "PM", "count": 5})
    assert resp.status_code == 200
    assert resp.json()["questions"][0]["question"] == "Q1"


def test_turn_is_scored(client: TestClient) -> None:
    resp = client.post("/interview/turn", json={"role": "PM", "answer": "I led a project"})
    assert resp.status_code == 200
    assert resp.json()["score"] == 75


def test_save_list_delete_session(client: TestClient) -> None:
    sid = client.post("/interview/sessions", json={"role": "PM", "overallScore": 80}).json()["id"]
    assert len(client.get("/interview/sessions").json()) == 1
    assert client.delete(f"/interview/sessions/{sid}").status_code == 204


def test_questions_rejects_count_over_max(client: TestClient) -> None:
    assert client.post("/interview/questions", json={"role": "PM", "count": 99}).status_code == 422


def test_turn_rejects_blank_answer(client: TestClient) -> None:
    assert client.post("/interview/turn", json={"role": "PM", "answer": ""}).status_code == 422
