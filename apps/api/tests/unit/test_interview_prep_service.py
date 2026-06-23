"""Unit tests for InterviewPrepService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.interview_prep.schemas import (
    QuestionRequest,
    QuestionSet,
    SessionCreate,
    TurnInput,
    TurnReply,
)
from src.domains.interview_prep.service import InterviewPrepService

pytestmark = pytest.mark.unit


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "questions": [
            {"question": "Tell me about a project", "category": "behavioral", "assesses": "impact", "answer_tips": ["STAR"]},
            {"category": "bad"},  # no question text — filtered out
        ],
        "feedback": "Good", "score": 80, "strengths": ["clear"], "improvements": ["depth"],
        "next_question": "Why us?", "done": False,
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "s1", **doc})
    r.list_for_user = AsyncMock(return_value=[])
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, llm) -> InterviewPrepService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return InterviewPrepService(repo, llm, sessions)


async def test_generate_questions_filters_invalid(service) -> None:
    qs = await service.generate_questions("u1", QuestionRequest(role="PM", count=6))
    assert isinstance(qs, QuestionSet)
    assert len(qs.questions) == 1  # the one without question text is dropped
    assert qs.questions[0].category == "behavioral"


async def test_generate_questions_fallback_on_llm_error(service, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    qs = await service.generate_questions("u1", QuestionRequest(role="PM"))
    assert qs.questions == []


async def test_turn_returns_scored_reply(service) -> None:
    out = await service.turn("u1", TurnInput(role="PM", answer="I led a team"))
    assert isinstance(out, TurnReply)
    assert out.score == 80
    assert out.next_question == "Why us?"


async def test_turn_coerces_non_numeric_score_to_zero(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value={"score": "high", "feedback": "f", "next_question": "q"})
    out = await service.turn("u1", TurnInput(role="PM", answer="x"))
    assert out.score == 0


async def test_save_session_returns_out(service) -> None:
    out = await service.save_session("u1", SessionCreate(role="PM", overall_score=70))
    assert out.id == "s1"
    assert out.overall_score == 70


async def test_delete_missing_raises(service, repo) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete_session("u1", "missing")
