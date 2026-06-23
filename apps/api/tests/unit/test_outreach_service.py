"""Unit tests for OutreachService (approval gate)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError
from src.domains.outreach.schemas import OutreachDraftRequest, OutreachEdit
from src.domains.outreach.service import OutreachService

pytestmark = pytest.mark.unit


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={"subject": "Hi", "body": "Let's connect"})
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "d1", **doc})
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock(side_effect=lambda did, uid, patch: {"id": did, "channel": "email", "tone": "warm", "goal": "g", **patch})
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, llm) -> OutreachService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return OutreachService(repo, llm, sessions)


async def test_draft_persists_as_draft_status(service, repo) -> None:
    out = await service.draft("u1", OutreachDraftRequest(goal="reconnect"))
    assert out.status == "draft"
    assert out.body == "Let's connect"


async def test_edit_reverts_to_draft(service, repo) -> None:
    await service.edit("u1", "d1", OutreachEdit(body="new body"))
    _did, _uid, patch = repo.update.call_args.args
    assert patch["status"] == "draft"
    assert patch["body"] == "new body"


async def test_edit_missing_raises(service, repo) -> None:
    repo.update = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.edit("u1", "missing", OutreachEdit(body="x"))


async def test_approve_happy(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "draft"})
    out = await service.approve("u1", "d1")
    assert out.status == "approved"


async def test_approve_already_sent_conflict(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "sent"})
    with pytest.raises(ConflictError):
        await service.approve("u1", "d1")


async def test_mark_sent_requires_approved(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "draft"})
    with pytest.raises(ConflictError):
        await service.mark_sent("u1", "d1")


async def test_mark_sent_happy(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "approved"})
    out = await service.mark_sent("u1", "d1")
    assert out.status == "sent"


async def test_delete_missing_raises(service, repo) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
