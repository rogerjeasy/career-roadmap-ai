"""Unit tests for the Skill Assessment flow.

Mocks the repository, LLM, session manager, evidence repo and credential service
— no Firestore, no network, no model calls. Covers quiz generation (answer key
kept server-side), grading → level mapping, the pass path that mints a verifiable
badge and records the measured skill, the fail path, and resilience when badge
minting fails.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ValidationError
from src.domains.assessments.schemas import (
    AssessmentOut,
    AssessmentStartInput,
    AssessmentSubmit,
    level_for_score,
)
from src.domains.assessments.service import AssessmentService
from src.session.models import UserProfileContext


# ── Pure schema logic ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [(90, "expert"), (85, "expert"), (70, "advanced"), (69, "intermediate"), (45, "intermediate"), (44, "beginner"), (0, "beginner")],
)
def test_level_for_score(score: int, expected: str) -> None:
    assert level_for_score(score) == expected


def test_out_does_not_expose_answer_key() -> None:
    out = AssessmentOut.from_doc(
        {
            "id": "a1",
            "skill": "SQL",
            "status": "in_progress",
            "questions": [{"id": "q1", "kind": "mcq", "prompt": "?", "options": ["a", "b"], "correct": "a"}],
            "answer_key": {"q1": {"correct": "a", "rubric": ""}},
        }
    )
    dumped = out.model_dump()
    assert "answer_key" not in dumped
    assert out.questions[0].model_dump() == {"id": "q1", "kind": "mcq", "prompt": "?", "options": ["a", "b"]}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.create = AsyncMock(side_effect=lambda user_id, data, **kw: {"id": "as1", "user_id": user_id, **data})
    m.get = AsyncMock(return_value=None)
    m.update = AsyncMock(side_effect=lambda _id, _uid, patch: {"id": _id, "skill": "Python", **patch})
    m.list_for_user = AsyncMock(return_value=[])
    return m


@pytest.fixture
def llm() -> MagicMock:
    return MagicMock(complete_json=AsyncMock(return_value={}))


@pytest.fixture
def sessions() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=SimpleNamespace(user_profile_context=UserProfileContext()))
    m.set_user_profile_context = AsyncMock()
    return m


@pytest.fixture
def evidence() -> MagicMock:
    return MagicMock(create=AsyncMock(return_value={"id": "ev1"}))


@pytest.fixture
def credentials() -> MagicMock:
    return MagicMock(issue=AsyncMock(return_value=SimpleNamespace(id="cred1")))


@pytest.fixture
def service(
    repo: MagicMock,
    llm: MagicMock,
    sessions: MagicMock,
    evidence: MagicMock,
    credentials: MagicMock,
) -> AssessmentService:
    return AssessmentService(repo, llm, sessions, evidence, credentials)


def _in_progress_doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "as1",
        "user_id": "u1",
        "skill": "Python",
        "status": "in_progress",
        "questions": [
            {"id": "q1", "kind": "mcq", "prompt": "Pick one", "options": ["a", "b", "c", "d"]},
            {"id": "q2", "kind": "short", "prompt": "Explain GIL"},
        ],
        "answer_key": {
            "q1": {"correct": "a", "rubric": ""},
            "q2": {"correct": "global lock", "rubric": "mentions one-thread-at-a-time"},
        },
    }
    base.update(over)
    return base


# ── start ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_builds_questions_and_hides_answer_key(
    service: AssessmentService, repo: MagicMock, llm: MagicMock
) -> None:
    llm.complete_json = AsyncMock(
        return_value={
            "questions": [
                {"kind": "mcq", "prompt": "Q1", "options": ["a", "b", "c", "d"], "correct": "a"},
                {"kind": "short", "prompt": "Q2", "correct": "model", "rubric": "covers X"},
            ]
        }
    )
    out = await service.start("u1", AssessmentStartInput(skill="Python", num_questions=3))

    assert out.status == "in_progress"
    # Stored count reflects the questions actually generated, not the request.
    assert out.num_questions == 2
    assert [q.kind for q in out.questions] == ["mcq", "short"]
    # The stored doc keeps an answer key keyed by the generated question ids…
    _uid, data = repo.create.call_args.args
    assert set(data["answer_key"].keys()) == {q["id"] for q in data["questions"]}
    # …but the public questions never carry the correct answer.
    assert all("correct" not in q for q in data["questions"])


@pytest.mark.asyncio
async def test_start_raises_when_llm_returns_nothing(
    service: AssessmentService, llm: MagicMock
) -> None:
    llm.complete_json = AsyncMock(return_value={})
    with pytest.raises(ValidationError):
        await service.start("u1", AssessmentStartInput(skill="Python"))


# ── submit / grade ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_pass_mints_badge_and_records_skill(
    service: AssessmentService,
    repo: MagicMock,
    llm: MagicMock,
    evidence: MagicMock,
    credentials: MagicMock,
    sessions: MagicMock,
) -> None:
    repo.get = AsyncMock(return_value=_in_progress_doc())
    llm.complete_json = AsyncMock(
        return_value={
            "score": 88,
            "summary": "Strong grasp.",
            "strengths": ["data model"],
            "gaps": [{"topic": "async", "note": "study event loop"}],
        }
    )
    out = await service.submit(
        "u1", "as1", "Ada", AssessmentSubmit(answers=[])
    )

    assert out.passed is True
    assert out.level == "expert"  # 88 → expert
    assert out.credential_id == "cred1"
    assert out.evidence_id == "ev1"
    evidence.create.assert_awaited_once()
    credentials.issue.assert_awaited_once()
    # Measured skill is written back into the session profile for the roadmap.
    sessions.set_user_profile_context.assert_awaited_once()
    saved_profile = sessions.set_user_profile_context.await_args.args[1]
    assert "python" in saved_profile.additional["assessed_skills"]


@pytest.mark.asyncio
async def test_submit_fail_does_not_mint_badge(
    service: AssessmentService,
    repo: MagicMock,
    llm: MagicMock,
    evidence: MagicMock,
    credentials: MagicMock,
    sessions: MagicMock,
) -> None:
    repo.get = AsyncMock(return_value=_in_progress_doc())
    llm.complete_json = AsyncMock(return_value={"score": 30, "summary": "Gaps.", "gaps": []})
    out = await service.submit("u1", "as1", "Ada", AssessmentSubmit(answers=[]))

    assert out.passed is False
    assert out.level == "beginner"
    assert out.credential_id is None
    evidence.create.assert_not_awaited()
    credentials.issue.assert_not_awaited()
    # The measured (failing) result is still recorded for the roadmap.
    sessions.set_user_profile_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_already_graded_raises(
    service: AssessmentService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=_in_progress_doc(status="graded"))
    with pytest.raises(ValidationError):
        await service.submit("u1", "as1", "Ada", AssessmentSubmit(answers=[]))


@pytest.mark.asyncio
async def test_submit_survives_badge_mint_failure(
    service: AssessmentService,
    repo: MagicMock,
    llm: MagicMock,
    evidence: MagicMock,
) -> None:
    repo.get = AsyncMock(return_value=_in_progress_doc())
    evidence.create = AsyncMock(side_effect=RuntimeError("firestore down"))
    llm.complete_json = AsyncMock(return_value={"score": 90, "summary": "ok", "gaps": []})

    out = await service.submit("u1", "as1", "Ada", AssessmentSubmit(answers=[]))

    # Grade still lands; the badge is simply absent.
    assert out.passed is True
    assert out.credential_id is None
    assert out.evidence_id is None
