"""Regression tests for the Ask-My-Journey domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.journey_qa.schemas import AskInput
from src.domains.journey_qa.service import JourneyQaService

pytestmark = pytest.mark.regression


class _FakeCol:
    async def list_for_user(self, uid, limit=0):
        return []


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(
        "src.domains.journey_qa.service.FirestoreCrudRepository",
        lambda db, name: _FakeCol(),
    )


def _service(llm) -> JourneyQaService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return JourneyQaService(MagicMock(), llm, sessions)


@pytest.mark.parametrize("bad", [None, [], "string", 123])
async def test_malformed_llm_output_never_crashes(bad) -> None:
    # REGRESSION: a hallucinated/non-JSON LLM response must degrade to a safe
    # fallback reply, never propagate an exception to the caller.
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value=bad)
    reply = await _service(llm).ask("u1", AskInput(question="x"))
    assert reply.answer
    assert isinstance(reply.sources, list)
    assert isinstance(reply.suggestions, list)
