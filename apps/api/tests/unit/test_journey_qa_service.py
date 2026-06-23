"""Unit tests for JourneyQaService (grounded Q&A over user data)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.journey_qa.schemas import AskInput, AskReply
from src.domains.journey_qa.service import JourneyQaService

pytestmark = pytest.mark.unit


class _FakeCol:
    async def list_for_user(self, uid, limit=0):
        return []


@pytest.fixture(autouse=True)
def _isolate_firestore(monkeypatch):
    monkeypatch.setattr(
        "src.domains.journey_qa.service.FirestoreCrudRepository",
        lambda db, name: _FakeCol(),
    )


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(
        return_value={"answer": "You have applied to 3 roles.", "sources": ["applications"], "suggestions": ["log evidence"]}
    )
    return m


@pytest.fixture
def service(llm: MagicMock) -> JourneyQaService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return JourneyQaService(MagicMock(), llm, sessions)


async def test_ask_returns_grounded_reply(service: JourneyQaService) -> None:
    reply = await service.ask("u1", AskInput(question="How many applications?"))
    assert isinstance(reply, AskReply)
    assert reply.answer == "You have applied to 3 roles."
    assert reply.sources == ["applications"]
    assert reply.suggestions == ["log evidence"]


async def test_ask_falls_back_when_llm_raises_value_error(service, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad json"))
    reply = await service.ask("u1", AskInput(question="x"))
    assert reply.answer  # non-empty fallback
    assert reply.sources == []


async def test_ask_falls_back_when_llm_returns_non_dict(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value=["not", "a", "dict"])
    reply = await service.ask("u1", AskInput(question="x"))
    assert "couldn't find enough data" in reply.answer.lower()
