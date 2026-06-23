"""Integration tests for the Assessments controller."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.assessments.schemas import (
    AssessmentOut,
    AssessmentStartInput,
    AssessmentSubmit,
    AssessmentSummary,
    QuizQuestion,
)
from src.domains.assessments.service import get_assessment_service
from src.domains.webhooks.service import get_webhook_service
from src.endpoints.v1.assessments_controller import router

pytestmark = pytest.mark.integration


class FakeAssessmentService:
    def __init__(self) -> None:
        self.store: dict[str, AssessmentOut] = {}
        self._seq = 0

    async def list(self, uid):
        return [AssessmentSummary(id=a.id, skill=a.skill, status=a.status, score=a.score, level=a.level, passed=a.passed) for a in self.store.values()]

    async def start(self, uid, payload: AssessmentStartInput):
        self._seq += 1
        aid = f"a{self._seq}"
        a = AssessmentOut(
            id=aid, skill=payload.skill, status="in_progress", num_questions=1,
            questions=[QuizQuestion(id="q1", kind="mcq", prompt="?", options=["a", "b"])],
        )
        self.store[aid] = a
        return a

    async def get(self, uid, assessment_id):
        if assessment_id not in self.store:
            raise NotFoundError("Assessment not found.")
        return self.store[assessment_id]

    async def submit(self, uid, assessment_id, holder_name, payload: AssessmentSubmit):
        if assessment_id not in self.store:
            raise NotFoundError("Assessment not found.")
        a = self.store[assessment_id]
        graded = a.model_copy(update={"status": "graded", "score": 80, "level": "advanced", "passed": True})
        self.store[assessment_id] = graded
        return graded


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeAssessmentService()
    webhooks = MagicMock()
    webhooks.dispatch = AsyncMock()
    app = make_app(
        router=router,
        overrides={get_assessment_service: lambda: service, get_webhook_service: lambda: webhooks},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_start_returns_questions_without_answers(client: TestClient) -> None:
    resp = client.post("/assessments", json={"skill": "SQL", "numQuestions": 6})
    assert resp.status_code == 201
    q = resp.json()["questions"][0]
    assert "correct" not in q  # answer key never leaves the server


def test_start_then_submit(client: TestClient) -> None:
    aid = client.post("/assessments", json={"skill": "SQL"}).json()["id"]
    resp = client.post(f"/assessments/{aid}/submit", json={"answers": [{"questionId": "q1", "answer": "a"}]})
    assert resp.status_code == 200
    assert resp.json()["passed"] is True


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/assessments/nope").status_code == 404


def test_start_rejects_too_few_questions(client: TestClient) -> None:
    assert client.post("/assessments", json={"skill": "SQL", "numQuestions": 1}).status_code == 422
