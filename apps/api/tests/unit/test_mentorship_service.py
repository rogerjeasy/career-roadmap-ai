"""Unit tests for MentorshipService (session lifecycle + matching)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.domains.mentorship.schemas import (
    CaseStudyCreate,
    SessionRequest,
    SessionRespond,
)
from src.domains.mentorship.service import MentorshipService

pytestmark = pytest.mark.unit


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.get_profile = AsyncMock(return_value={"user_id": "m1", "name": "Mentor", "is_active": True})
    r.create_session = AsyncMock(side_effect=lambda doc: {"id": "s1", "status": "requested", **doc})
    r.get_session = AsyncMock(return_value=None)
    r.update_session = AsyncMock(side_effect=lambda sid, patch: {"id": sid, "mentor_id": "m1", "mentee_id": "u1", **patch})
    r.list_sessions_for = AsyncMock(return_value=[])
    r.list_active_profiles = AsyncMock(return_value=[])
    r.list_cases = AsyncMock(return_value=[])
    r.create_case = AsyncMock(side_effect=lambda uid, name, doc: {"id": "c1", "author_id": uid, "author_name": name, **doc})
    r.get_case = AsyncMock(return_value=None)
    r.soft_delete_case = AsyncMock()
    return r


@pytest.fixture
def service(repo) -> MentorshipService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return MentorshipService(repo, sessions)


# ── request_session ─────────────────────────────────────────────────────────────


async def test_request_session_rejects_self(service) -> None:
    with pytest.raises(ValidationError):
        await service.request_session("u1", "U", SessionRequest(mentor_id="u1", topic="t"))


async def test_request_session_inactive_mentor_raises(service, repo) -> None:
    repo.get_profile = AsyncMock(return_value={"user_id": "m1", "is_active": False})
    with pytest.raises(NotFoundError):
        await service.request_session("u1", "U", SessionRequest(mentor_id="m1", topic="t"))


async def test_request_session_happy(service) -> None:
    out = await service.request_session("u1", "U", SessionRequest(mentor_id="m1", topic="Career"))
    assert out.status == "requested"
    assert out.role == "mentee"


# ── respond_session ─────────────────────────────────────────────────────────────


async def test_respond_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.respond_session("m1", "s1", SessionRespond(decision="accepted"))


async def test_respond_non_mentor_forbidden(service, repo) -> None:
    repo.get_session = AsyncMock(return_value={"id": "s1", "mentor_id": "m1", "status": "requested"})
    with pytest.raises(AuthorizationError):
        await service.respond_session("someone_else", "s1", SessionRespond(decision="accepted"))


async def test_respond_already_answered_conflict(service, repo) -> None:
    repo.get_session = AsyncMock(return_value={"id": "s1", "mentor_id": "m1", "status": "accepted"})
    with pytest.raises(ConflictError):
        await service.respond_session("m1", "s1", SessionRespond(decision="declined"))


async def test_respond_happy(service, repo) -> None:
    repo.get_session = AsyncMock(return_value={"id": "s1", "mentor_id": "m1", "mentee_id": "u1", "status": "requested"})
    out = await service.respond_session("m1", "s1", SessionRespond(decision="accepted", reply="Sure"))
    assert out.status == "accepted"


# ── complete_session ────────────────────────────────────────────────────────────


async def test_complete_requires_membership(service, repo) -> None:
    repo.get_session = AsyncMock(return_value={"id": "s1", "mentor_id": "m1", "mentee_id": "u1", "status": "accepted"})
    with pytest.raises(AuthorizationError):
        await service.complete_session("stranger", "s1")


async def test_complete_requires_accepted_status(service, repo) -> None:
    repo.get_session = AsyncMock(return_value={"id": "s1", "mentor_id": "m1", "mentee_id": "u1", "status": "requested"})
    with pytest.raises(ConflictError):
        await service.complete_session("u1", "s1")


# ── case studies ────────────────────────────────────────────────────────────────


async def test_delete_case_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.delete_case_study("u1", "c1")


async def test_delete_case_non_author_forbidden(service, repo) -> None:
    repo.get_case = AsyncMock(return_value={"id": "c1", "author_id": "other", "deleted_at": None})
    with pytest.raises(AuthorizationError):
        await service.delete_case_study("u1", "c1")


async def test_create_case_study(service) -> None:
    out = await service.create_case_study(
        "u1", "Ada", CaseStudyCreate(from_role="Dev", to_role="Lead", summary="grew")
    )
    assert out.from_role == "Dev"
    assert out.is_mine is True


# ── discovery / matching ────────────────────────────────────────────────────────


async def test_discover_excludes_self_and_ranks(service, repo) -> None:
    repo.list_active_profiles = AsyncMock(return_value=[
        {"user_id": "u1", "headline": "me"},  # self — excluded
        {"user_id": "m2", "headline": "Data lead", "expertise": ["python", "sql"]},
    ])
    out = await service.discover_mentors("u1")
    assert all(m.user_id != "u1" for m in out)
    assert len(out) == 1


def test_match_without_interest_returns_zero() -> None:
    score, reason = MentorshipService._match(set(), {"expertise": ["python"]})
    assert score == 0
    assert "target role" in reason.lower()


def test_match_with_overlap_scores_and_explains() -> None:
    score, reason = MentorshipService._match({"python", "sql"}, {"expertise": ["Python", "Go"]})
    assert score > 0
    assert "python" in reason.lower()
