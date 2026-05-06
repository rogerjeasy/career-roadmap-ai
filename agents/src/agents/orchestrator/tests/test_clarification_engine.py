"""Tests for ClarificationEngine.

Covers: score(), generate_questions(), parse_answers(), apply_answers().
All LLM calls are mocked; no network required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.tasks import UserProfileSnapshot
from agents.orchestrator.clarification_engine import (
    ClarificationEngine,
    ClarificationQuestion,
    _coerce_parsed_values,
    _fallback_question,
    _fast_score,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def engine(mock_llm: AsyncMock) -> ClarificationEngine:
    return ClarificationEngine(llm=mock_llm)


@pytest.fixture
def full_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="Senior ML Engineer",
        current_role="Backend Developer",
        skills=["Python", "SQL"],
        location="Berlin, Germany",
        timeline_months=12,
        weekly_hours_available=10,
        salary_goal=120_000,
    )


@pytest.fixture
def empty_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot()


def _llm_response(content: str) -> MagicMock:
    """Build a mock LLM response with the given string content."""
    m = MagicMock()
    m.content = content
    return m


# ── ClarificationQuestion ─────────────────────────────────────────────────────


class TestClarificationQuestion:
    def test_to_dict_round_trips(self) -> None:
        q = ClarificationQuestion(question="What role?", field_name="target_role", priority=1)
        assert ClarificationQuestion.from_dict(q.to_dict()) == q

    def test_default_id_is_unique(self) -> None:
        q1 = ClarificationQuestion(question="Q", field_name="target_role")
        q2 = ClarificationQuestion(question="Q", field_name="target_role")
        assert q1.id != q2.id

    def test_from_dict_uses_existing_id(self) -> None:
        d = {"question": "Q", "field_name": "target_role", "priority": 2, "id": "fixed-id"}
        q = ClarificationQuestion.from_dict(d)
        assert q.id == "fixed-id"
        assert q.priority == 2


# ── score() ───────────────────────────────────────────────────────────────────


class TestScore:
    def test_full_profile_scores_1(self, engine: ClarificationEngine, full_profile: UserProfileSnapshot) -> None:
        score, missing = engine.score(full_profile)
        assert score == pytest.approx(1.0)
        assert missing == []

    def test_empty_profile_scores_0(self, engine: ClarificationEngine, empty_profile: UserProfileSnapshot) -> None:
        score, missing = engine.score(empty_profile)
        assert score == pytest.approx(0.0)
        assert set(missing) == {
            "target_role", "current_role", "skills",
            "location", "timeline_months", "weekly_hours_available", "salary_goal",
        }

    def test_partial_profile(self, engine: ClarificationEngine) -> None:
        # target_role=0.30 + current_role=0.15 + timeline_months=0.15 = 0.60
        profile = UserProfileSnapshot(
            target_role="ML Engineer",
            current_role="Backend Dev",
            timeline_months=12,
        )
        score, missing = engine.score(profile)
        assert score == pytest.approx(0.60)
        assert "skills" in missing
        assert "target_role" not in missing

    def test_skills_empty_list_counts_as_missing(self, engine: ClarificationEngine) -> None:
        profile = UserProfileSnapshot(skills=[])
        score, missing = engine.score(profile)
        assert "skills" in missing

    def test_skills_non_empty_list_counts_as_present(self, engine: ClarificationEngine) -> None:
        profile = UserProfileSnapshot(skills=["Python"])
        _, missing = engine.score(profile)
        assert "skills" not in missing

    def test_score_is_deterministic(self, engine: ClarificationEngine, full_profile: UserProfileSnapshot) -> None:
        assert engine.score(full_profile) == engine.score(full_profile)


# ── generate_questions() ──────────────────────────────────────────────────────


class TestGenerateQuestions:
    async def test_returns_empty_when_no_missing_slots(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        questions = await engine.generate_questions(
            profile=UserProfileSnapshot(),
            missing_slots=[],
            user_message="any",
        )
        assert questions == []
        mock_llm.ainvoke.assert_not_called()

    async def test_llm_questions_returned_as_dataclass(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _llm_response(
            '[{"question": "What role?", "field_name": "target_role", "priority": 1}]'
        )
        questions = await engine.generate_questions(
            profile=UserProfileSnapshot(),
            missing_slots=["target_role"],
            user_message="I want to transition",
        )
        assert len(questions) == 1
        assert isinstance(questions[0], ClarificationQuestion)
        assert questions[0].field_name == "target_role"

    async def test_fallback_on_llm_failure(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("LLM down")
        questions = await engine.generate_questions(
            profile=UserProfileSnapshot(),
            missing_slots=["target_role", "skills"],
            user_message="career change",
        )
        assert len(questions) >= 1
        assert all(isinstance(q, ClarificationQuestion) for q in questions)
        assert all(q.field_name in ("target_role", "skills") for q in questions)

    async def test_respects_n_cap(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _llm_response(
            '[{"question": "Q1", "field_name": "target_role", "priority": 1},'
            ' {"question": "Q2", "field_name": "skills", "priority": 2},'
            ' {"question": "Q3", "field_name": "location", "priority": 3},'
            ' {"question": "Q4", "field_name": "timeline_months", "priority": 4}]'
        )
        questions = await engine.generate_questions(
            profile=UserProfileSnapshot(),
            missing_slots=["target_role", "skills", "location", "timeline_months"],
            user_message="msg",
            n=2,
        )
        # n=2 was passed but max_clarification_questions may be smaller
        assert len(questions) <= 2

    async def test_prioritises_highest_weight_slot(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        """target_role (0.30) must be in the first LLM call over salary_goal (0.05)."""
        captured: list[str] = []

        async def capture(*args, **kwargs):
            msg = str(args[0][-1].content)
            captured.append(msg)
            return _llm_response(
                '[{"question": "Q?", "field_name": "target_role", "priority": 1}]'
            )

        mock_llm.ainvoke.side_effect = capture
        await engine.generate_questions(
            profile=UserProfileSnapshot(),
            missing_slots=["salary_goal", "target_role"],
            user_message="msg",
            n=1,
        )
        assert "target_role" in captured[0]
        assert "salary_goal" not in captured[0]


# ── parse_answers() ───────────────────────────────────────────────────────────


class TestParseAnswers:
    async def test_returns_empty_when_no_questions(
        self, engine: ClarificationEngine
    ) -> None:
        result = await engine.parse_answers([], "I am a backend developer")
        assert result == {}

    async def test_returns_empty_when_blank_response(
        self, engine: ClarificationEngine
    ) -> None:
        q = ClarificationQuestion(question="What role?", field_name="target_role")
        result = await engine.parse_answers([q], "   ")
        assert result == {}

    async def test_parsed_fields_returned(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _llm_response(
            '{"target_role": "ML Engineer", "skills": ["Python", "TensorFlow"]}'
        )
        questions = [
            ClarificationQuestion(question="What role?", field_name="target_role"),
            ClarificationQuestion(question="What skills?", field_name="skills"),
        ]
        result = await engine.parse_answers(questions, "I want to be an ML Engineer")
        assert result["target_role"] == "ML Engineer"
        assert "Python" in result["skills"]

    async def test_returns_empty_on_llm_failure(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.side_effect = Exception("Network error")
        q = ClarificationQuestion(question="What role?", field_name="target_role")
        result = await engine.parse_answers([q], "ML Engineer")
        assert result == {}

    async def test_coerces_timeline_to_int(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        mock_llm.ainvoke.return_value = _llm_response('{"timeline_months": 12}')
        q = ClarificationQuestion(question="Timeline?", field_name="timeline_months")
        result = await engine.parse_answers([q], "12 months")
        assert result["timeline_months"] == 12
        assert isinstance(result["timeline_months"], int)


# ── apply_answers() ───────────────────────────────────────────────────────────


class TestApplyAnswers:
    def test_applies_to_empty_profile(
        self, engine: ClarificationEngine, empty_profile: UserProfileSnapshot
    ) -> None:
        updated, applied = engine.apply_answers(
            empty_profile,
            {"target_role": "ML Engineer", "timeline_months": 12},
        )
        assert updated.target_role == "ML Engineer"
        assert updated.timeline_months == 12
        assert set(applied) == {"target_role", "timeline_months"}

    def test_does_not_mutate_original(
        self, engine: ClarificationEngine, empty_profile: UserProfileSnapshot
    ) -> None:
        engine.apply_answers(empty_profile, {"target_role": "ML Engineer"})
        assert empty_profile.target_role is None

    def test_skills_are_merged_not_replaced(
        self, engine: ClarificationEngine
    ) -> None:
        profile = UserProfileSnapshot(skills=["Python"])
        updated, _ = engine.apply_answers(profile, {"skills": ["TensorFlow", "Python"]})
        assert "Python" in updated.skills
        assert "TensorFlow" in updated.skills
        # Original Python appears only once
        assert updated.skills.count("Python") == 1

    def test_ignores_unknown_fields(
        self, engine: ClarificationEngine, empty_profile: UserProfileSnapshot
    ) -> None:
        updated, applied = engine.apply_answers(
            empty_profile, {"nonexistent_field": "value"}
        )
        assert applied == []
        assert updated == empty_profile

    def test_ignores_none_values(
        self, engine: ClarificationEngine, empty_profile: UserProfileSnapshot
    ) -> None:
        updated, applied = engine.apply_answers(
            empty_profile, {"target_role": None}
        )
        assert applied == []
        assert updated.target_role is None

    def test_empty_answers_returns_original(
        self, engine: ClarificationEngine, full_profile: UserProfileSnapshot
    ) -> None:
        updated, applied = engine.apply_answers(full_profile, {})
        assert updated == full_profile
        assert applied == []

    def test_overwrites_existing_scalar(
        self, engine: ClarificationEngine
    ) -> None:
        profile = UserProfileSnapshot(target_role="Backend Dev")
        updated, applied = engine.apply_answers(
            profile, {"target_role": "ML Engineer"}
        )
        assert updated.target_role == "ML Engineer"
        assert "target_role" in applied


# ── _coerce_parsed_values() ───────────────────────────────────────────────────


class TestCoerceParsedValues:
    def test_strips_string_whitespace(self) -> None:
        result = _coerce_parsed_values({"target_role": "  ML Engineer  "})
        assert result["target_role"] == "ML Engineer"

    def test_splits_comma_separated_skills(self) -> None:
        result = _coerce_parsed_values({"skills": "Python, SQL, React"})
        assert result["skills"] == ["Python", "SQL", "React"]

    def test_splits_semicolon_separated_skills(self) -> None:
        result = _coerce_parsed_values({"skills": "Python;SQL"})
        assert "Python" in result["skills"]
        assert "SQL" in result["skills"]

    def test_skill_list_passthrough(self) -> None:
        result = _coerce_parsed_values({"skills": ["Python", "SQL"]})
        assert result["skills"] == ["Python", "SQL"]

    def test_coerces_int_from_float(self) -> None:
        result = _coerce_parsed_values({"timeline_months": 12.0})
        assert result["timeline_months"] == 12
        assert isinstance(result["timeline_months"], int)

    def test_coerces_salary_from_string(self) -> None:
        result = _coerce_parsed_values({"salary_goal": "120,000"})
        assert result["salary_goal"] == 120000

    def test_skips_unknown_slots(self) -> None:
        result = _coerce_parsed_values({"mystery_field": "value"})
        assert "mystery_field" not in result

    def test_skips_none_values(self) -> None:
        result = _coerce_parsed_values({"target_role": None})
        assert "target_role" not in result

    def test_skips_empty_string(self) -> None:
        result = _coerce_parsed_values({"target_role": ""})
        assert "target_role" not in result


# ── _fast_score() ─────────────────────────────────────────────────────────────


class TestFastScore:
    def test_agrees_with_engine_score(self, engine: ClarificationEngine, full_profile: UserProfileSnapshot) -> None:
        engine_score, _ = engine.score(full_profile)
        assert _fast_score(full_profile) == engine_score

    def test_zero_for_empty_profile(self, empty_profile: UserProfileSnapshot) -> None:
        assert _fast_score(empty_profile) == pytest.approx(0.0)


# ── _fallback_question() ──────────────────────────────────────────────────────


class TestFallbackQuestion:
    def test_known_slot_returns_specific_question(self) -> None:
        q = _fallback_question("target_role")
        assert "role" in q.lower()

    def test_unknown_slot_returns_generic_question(self) -> None:
        q = _fallback_question("completely_unknown_field")
        assert "completely unknown field" in q


# ── End-to-end: score → generate → parse → apply ─────────────────────────────


class TestClarificationRoundTrip:
    async def test_full_round_lifts_score(
        self, engine: ClarificationEngine, mock_llm: AsyncMock
    ) -> None:
        """Simulate one complete clarification cycle and verify score improves."""
        profile = UserProfileSnapshot()
        score_before, missing = engine.score(profile)
        assert score_before < 0.5

        # Mock: question generation
        mock_llm.ainvoke.return_value = _llm_response(
            '[{"question": "What role?", "field_name": "target_role", "priority": 1}]'
        )
        questions = await engine.generate_questions(
            profile, missing[:1], "I want to switch careers"
        )
        assert len(questions) == 1

        # Mock: answer parsing (separate call)
        mock_llm.ainvoke.return_value = _llm_response(
            '{"target_role": "ML Engineer"}'
        )
        parsed = await engine.parse_answers(questions, "I want to be an ML Engineer")
        assert parsed.get("target_role") == "ML Engineer"

        updated, applied = engine.apply_answers(profile, parsed)
        assert "target_role" in applied
        score_after, _ = engine.score(updated)
        assert score_after > score_before
