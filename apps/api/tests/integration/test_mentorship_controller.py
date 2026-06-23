"""Integration tests for the Mentorship controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from src.domains.mentorship.schemas import (
    CaseStudyCreate,
    CaseStudyOut,
    MentorProfileOut,
    MentorProfileUpsert,
    MentorSessionOut,
    SessionRequest,
    SessionRespond,
)
from src.domains.mentorship.service import get_mentorship_service
from src.endpoints.v1.mentorship_controller import router

pytestmark = pytest.mark.integration


class FakeMentorshipService:
    def __init__(self) -> None:
        self.profile: MentorProfileOut | None = None
        self.sessions: dict[str, MentorSessionOut] = {}
        self.cases: dict[str, CaseStudyOut] = {}
        self._seq = 0

    async def get_my_profile(self, uid):
        return self.profile

    async def upsert_profile(self, uid, name, payload: MentorProfileUpsert):
        self.profile = MentorProfileOut(
            user_id=uid, name=name, headline=payload.headline, bio=payload.bio,
            expertise=payload.expertise, capacity=payload.capacity, is_active=payload.is_active,
        )
        return self.profile

    async def deactivate_profile(self, uid):
        self.profile = None

    async def discover_mentors(self, uid):
        return []

    async def list_my_sessions(self, uid):
        return list(self.sessions.values())

    async def request_session(self, uid, name, payload: SessionRequest):
        self._seq += 1
        sid = f"s{self._seq}"
        s = MentorSessionOut(
            id=sid, mentor_id=payload.mentor_id, mentor_name="M", mentee_id=uid,
            mentee_name=name, topic=payload.topic, message=payload.message, reply="",
            status="requested", role="mentee",
        )
        self.sessions[sid] = s
        return s

    async def respond_session(self, uid, session_id, payload: SessionRespond):
        if session_id not in self.sessions:
            raise NotFoundError("Session not found.")
        s = self.sessions[session_id]
        if s.mentor_id != uid:
            raise AuthorizationError("Only the mentor can respond.")
        if s.status != "requested":
            raise ConflictError("Already answered.")
        s.status = payload.decision
        return s

    async def complete_session(self, uid, session_id):
        if session_id not in self.sessions:
            raise NotFoundError("Session not found.")
        return self.sessions[session_id]

    async def list_case_studies(self, uid):
        return list(self.cases.values())

    async def create_case_study(self, uid, name, payload: CaseStudyCreate):
        self._seq += 1
        cid = f"c{self._seq}"
        c = CaseStudyOut(
            id=cid, author_name=name, from_role=payload.from_role, to_role=payload.to_role,
            timeframe_months=payload.timeframe_months, summary=payload.summary,
            steps=payload.steps, lessons=payload.lessons, is_mine=True,
        )
        self.cases[cid] = c
        return c

    async def delete_case_study(self, uid, case_id):
        if case_id not in self.cases:
            raise NotFoundError("Case study not found.")
        del self.cases[case_id]


@pytest.fixture
def service() -> FakeMentorshipService:
    return FakeMentorshipService()


@pytest.fixture
def client(make_app, user, service: FakeMentorshipService) -> TestClient:
    app = make_app(
        router=router,
        overrides={get_mentorship_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_profile_get_null_then_upsert_then_deactivate(client: TestClient) -> None:
    assert client.get("/mentorship/profile").json() is None
    up = client.put("/mentorship/profile", json={"headline": "Staff Eng"})
    assert up.status_code == 200
    assert up.json()["headline"] == "Staff Eng"
    assert client.delete("/mentorship/profile").status_code == 204


def test_request_session_returns_201(client: TestClient) -> None:
    resp = client.post("/mentorship/sessions", json={"mentorId": "m1", "topic": "Growth"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "requested"


def test_mentor_can_respond_to_a_request(client: TestClient, service: FakeMentorshipService, user) -> None:
    # Seed a request where the current user is the mentor.
    service.sessions["s1"] = MentorSessionOut(
        id="s1", mentor_id=user.uid, mentor_name="Me", mentee_id="other",
        mentee_name="Mentee", topic="t", message="", reply="", status="requested", role="mentor",
    )
    resp = client.post("/mentorship/sessions/s1/respond", json={"decision": "accepted"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


def test_respond_missing_session_404(client: TestClient) -> None:
    assert client.post("/mentorship/sessions/nope/respond", json={"decision": "declined"}).status_code == 404


def test_case_study_create_list_delete(client: TestClient) -> None:
    cid = client.post(
        "/mentorship/case-studies",
        json={"fromRole": "Dev", "toRole": "Lead", "summary": "grew"},
    ).json()["id"]
    assert len(client.get("/mentorship/case-studies").json()) == 1
    assert client.delete(f"/mentorship/case-studies/{cid}").status_code == 204


def test_request_session_rejects_blank_topic(client: TestClient) -> None:
    assert client.post("/mentorship/sessions", json={"mentorId": "m1", "topic": ""}).status_code == 422
