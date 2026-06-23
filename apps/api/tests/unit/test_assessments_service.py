"""Unit tests for AssessmentService (quiz generation + grading + badges)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.assessments.schemas import (
    AssessmentAnswer,
    AssessmentOut,
    AssessmentStartInput,
    AssessmentSubmit,
    level_for_score,
)
from src.domains.assessments.service import AssessmentService, _clamp_score

pytestmark = pytest.mark.unit


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "questions": [
            {"kind": "mcq", "prompt": "2+2?", "options": ["3", "4", "5", "6"], "correct": "4"},
            {"kind": "short", "prompt": "Explain X", "correct": "model", "rubric": "mentions Y"},
        ]
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "a1", **doc})
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock(side_effect=lambda aid, uid, patch: {"id": aid, "skill": "SQL", "questions": [], **patch})
    return r


@pytest.fixture
def credentials() -> MagicMock:
    c = MagicMock()
    c.issue = AsyncMock(return_value=MagicMock(id="cred1"))
    return c


@pytest.fixture
def evidence() -> MagicMock:
    e = MagicMock()
    e.create = AsyncMock(return_value={"id": "ev1"})
    return e


@pytest.fixture
def service(repo, llm, evidence, credentials) -> AssessmentService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return AssessmentService(repo, llm, sessions, evidence, credentials)


# ── pure helpers ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("score", "level"), [(90, "expert"), (75, "advanced"), (50, "intermediate"), (10, "beginner")])
def test_level_for_score(score, level) -> None:
    assert level_for_score(score) == level


@pytest.mark.parametrize(("raw", "expected"), [(150, 100), (-5, 0), ("80", 80), ("nan", 0), (None, 0)])
def test_clamp_score(raw, expected) -> None:
    assert _clamp_score(raw) == expected


# ── start ─────────────────────────────────────────────────────────────────────


async def test_start_builds_quiz_without_exposing_answer_key(service, repo) -> None:
    out = await service.start("u1", AssessmentStartInput(skill="SQL", num_questions=6))
    assert out.status == "in_progress"
    assert len(out.questions) == 2
    # The stored doc keeps an answer_key, but the client-facing model never does.
    _uid, stored = repo.create.call_args.args
    assert "answer_key" in stored
    dumped = out.model_dump()
    assert "answer_key" not in dumped
    assert all("correct" not in q for q in dumped["questions"])


async def test_start_empty_generation_raises(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value={"questions": []})
    with pytest.raises(ValidationError):
        await service.start("u1", AssessmentStartInput(skill="SQL"))


# ── submit ──────────────────────────────────────────────────────────────────────


async def test_submit_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.submit("u1", "missing", "Ada", AssessmentSubmit(answers=[]))


async def test_submit_already_graded_raises(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "a1", "status": "graded"})
    with pytest.raises(ValidationError):
        await service.submit("u1", "a1", "Ada", AssessmentSubmit(answers=[]))


async def test_submit_pass_mints_badge(service, repo, llm, credentials, evidence) -> None:
    repo.get = AsyncMock(return_value={"id": "a1", "status": "in_progress", "skill": "SQL", "questions": [{"id": "q1", "kind": "mcq", "prompt": "?"}], "answer_key": {"q1": {"correct": "4"}}})
    llm.complete_json = AsyncMock(return_value={"score": 88, "summary": "great", "strengths": [], "gaps": []})
    out = await service.submit("u1", "a1", "Ada", AssessmentSubmit(answers=[AssessmentAnswer(question_id="q1", answer="4")]))
    assert out.passed is True
    assert out.level == "expert"
    credentials.issue.assert_awaited_once()
    evidence.create.assert_awaited_once()


async def test_submit_fail_does_not_mint_badge(service, repo, llm, credentials) -> None:
    repo.get = AsyncMock(return_value={"id": "a1", "status": "in_progress", "skill": "SQL", "questions": [], "answer_key": {}})
    llm.complete_json = AsyncMock(return_value={"score": 30, "summary": "weak", "strengths": [], "gaps": []})
    out = await service.submit("u1", "a1", "Ada", AssessmentSubmit(answers=[]))
    assert out.passed is False
    credentials.issue.assert_not_called()
