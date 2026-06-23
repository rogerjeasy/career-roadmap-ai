"""Unit tests for CareerTwinService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError
from src.domains.career_twin.schemas import DailyCheckinOut, TwinPersonaOut, TwinPersonaUpsert
from src.domains.career_twin.service import CareerTwinService, _today

pytestmark = pytest.mark.unit


@pytest.fixture
def persona_repo() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value={"name": "Coach", "voice": "direct"})
    r.create = AsyncMock(side_effect=lambda uid, doc, doc_id=None: doc)
    r.update = AsyncMock(side_effect=lambda uid, did, doc: doc)
    return r


@pytest.fixture
def checkin_repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "ck1", **doc})
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock(side_effect=lambda cid, uid, patch: {"id": cid, "date": _today(), "greeting": "g", "prompt": "p", "focus_suggestion": "", **patch})
    return r


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={"greeting": "Hey!", "prompt": "What today?", "focus_suggestion": "Ship it", "response": "Nice work."})
    return m


@pytest.fixture
def service(persona_repo, checkin_repo, llm) -> CareerTwinService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return CareerTwinService(persona_repo, checkin_repo, llm, sessions)


async def test_get_persona_defaults_when_absent(service, persona_repo) -> None:
    persona_repo.get = AsyncMock(return_value=None)
    p = await service.get_persona("u1")
    assert isinstance(p, TwinPersonaOut)
    assert p.name == "Your Career Twin"


async def test_upsert_creates_when_absent(service, persona_repo) -> None:
    persona_repo.get = AsyncMock(return_value=None)
    await service.upsert_persona("u1", TwinPersonaUpsert(name="Mentor", voice="direct"))
    persona_repo.create.assert_awaited_once()
    persona_repo.update.assert_not_called()


async def test_upsert_updates_when_present(service, persona_repo) -> None:
    await service.upsert_persona("u1", TwinPersonaUpsert(name="Mentor"))
    persona_repo.update.assert_awaited_once()


async def test_today_creates_when_none_exists(service, checkin_repo) -> None:
    out = await service.today("u1")
    assert isinstance(out, DailyCheckinOut)
    assert out.status == "open"
    checkin_repo.create.assert_awaited_once()


async def test_today_returns_existing_for_date(service, checkin_repo) -> None:
    checkin_repo.list_for_user = AsyncMock(return_value=[{"id": "ck1", "date": _today(), "status": "open"}])
    out = await service.today("u1")
    assert out.id == "ck1"
    checkin_repo.create.assert_not_called()


async def test_today_opening_falls_back_when_llm_fails(service, checkin_repo, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    await service.today("u1")
    _uid, doc = checkin_repo.create.call_args.args
    assert doc["greeting"]  # non-empty fallback greeting
    assert doc["prompt"]


async def test_reply_missing_raises(service, checkin_repo) -> None:
    with pytest.raises(NotFoundError):
        await service.reply("u1", "missing", "done stuff", None)


async def test_reply_already_answered_conflict(service, checkin_repo) -> None:
    checkin_repo.get = AsyncMock(return_value={"id": "ck1", "status": "answered"})
    with pytest.raises(ConflictError):
        await service.reply("u1", "ck1", "again", None)


async def test_reply_happy_sets_twin_response(service, checkin_repo) -> None:
    checkin_repo.get = AsyncMock(return_value={"id": "ck1", "status": "open", "prompt": "p"})
    out = await service.reply("u1", "ck1", "I shipped", 4)
    assert out.status == "answered"
    assert out.twin_response == "Nice work."
