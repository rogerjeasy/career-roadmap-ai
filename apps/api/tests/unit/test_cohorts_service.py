"""Unit tests for CohortService (membership lifecycle + matching)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from src.domains.cohorts.schemas import CheckinCreate, CohortCreate
from src.domains.cohorts.service import CohortService

pytestmark = pytest.mark.unit


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, name, doc: {"id": "c1", "created_by": uid, "member_ids": [uid], "members": [{"uid": uid, "name": name}], **doc})
    r.list_for_member = AsyncMock(return_value=[])
    r.list_open = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock(side_effect=lambda cid, patch: {"id": cid, "created_by": "owner", **patch})
    r.soft_delete = AsyncMock()
    r.list_checkins = AsyncMock(return_value=[])
    r.add_checkin = AsyncMock(return_value={"id": "ck1", "cohort_id": "c1", "user_id": "u1", "user_name": "U", "done": "stuff"})
    return r


@pytest.fixture
def service(repo) -> CohortService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return CohortService(repo, sessions)


async def test_create_returns_owner_cohort(service) -> None:
    out = await service.create("u1", "Ada", CohortCreate(name="Job Hunt", focus="PM roles"))
    assert out.is_owner is True
    assert out.is_member is True


async def test_join_full_cohort_raises(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["a", "b"], "capacity": 2, "members": []})
    with pytest.raises(ConflictError):
        await service.join("u1", "U", "c1")


async def test_join_existing_member_is_idempotent(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["u1"], "capacity": 6, "members": [{"uid": "u1", "name": "U"}]})
    out = await service.join("u1", "U", "c1")
    assert out.is_member is True
    repo.update.assert_not_called()


async def test_join_adds_member(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["a"], "capacity": 6, "members": [{"uid": "a", "name": "A"}]})
    await service.join("u1", "U", "c1")
    _cid, patch = repo.update.call_args.args
    assert "u1" in patch["member_ids"]


async def test_join_missing_cohort_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.join("u1", "U", "missing")


async def test_leave_last_member_archives(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["u1"], "members": [{"uid": "u1"}], "capacity": 6})
    await service.leave("u1", "c1")
    repo.soft_delete.assert_awaited_once_with("c1")


async def test_leave_updates_remaining(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["u1", "b"], "members": [{"uid": "u1"}, {"uid": "b"}], "capacity": 6})
    await service.leave("u1", "c1")
    _cid, patch = repo.update.call_args.args
    assert patch["member_ids"] == ["b"]


async def test_dashboard_requires_membership(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["other"]})
    with pytest.raises(AuthorizationError):
        await service.dashboard("u1", "c1")


async def test_post_checkin_requires_membership(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["other"]})
    with pytest.raises(AuthorizationError):
        await service.post_checkin("u1", "U", "c1", CheckinCreate(done="x"))


async def test_post_checkin_member_ok(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "c1", "member_ids": ["u1"]})
    out = await service.post_checkin("u1", "U", "c1", CheckinCreate(done="shipped"))
    assert out.id == "ck1"


async def test_discover_excludes_joined_and_full(service, repo) -> None:
    repo.list_open = AsyncMock(return_value=[
        {"id": "a", "member_ids": ["u1"], "capacity": 6},   # already joined
        {"id": "b", "member_ids": ["x", "y"], "capacity": 2},  # full
        {"id": "c", "member_ids": ["x"], "capacity": 6, "focus": "PM"},  # available
    ])
    out = await service.discover("u1")
    assert [c.id for c in out] == ["c"]


def test_match_without_interest_returns_zero() -> None:
    score, reason = CohortService._match(set(), {"focus": "PM roles"})
    assert score == 0
