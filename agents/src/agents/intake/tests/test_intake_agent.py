"""Tests for the Intake & Profile Agent.

Covers:
  - SlotExtractor: extraction, fallback on LLM failure, empty text, coercion
  - ProfileBuilder: merge rules for scalars, lists, no-change, completeness
  - IntakeAgent: full pipeline, progress events, empty message, partial profile
  - missing_slots / completeness_score helpers

All LLM calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.intake.intake_agent import IntakeAgent, _CLARIFICATION_THRESHOLD
from agents.intake.models import ExtractedSlot, ProfileDiff, SlotExtractionResult
from agents.intake.profile_builder import (
    ProfileBuilder,
    completeness_score,
    missing_slots,
    _merge_list,
)
from agents.intake.slot_extractor import SlotExtractor, _coerce, _parse_llm_output


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def extractor(mock_llm: AsyncMock) -> SlotExtractor:
    return SlotExtractor(llm=mock_llm)


@pytest.fixture
def builder() -> ProfileBuilder:
    return ProfileBuilder()


@pytest.fixture
def empty_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot()


@pytest.fixture
def partial_profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="Senior ML Engineer",
        current_role="Backend Developer",
        skills=["Python", "SQL"],
    )


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


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _make_context(
    profile: UserProfileSnapshot | None = None,
    user_message: str = "I am a Python dev aiming for ML engineer in 12 months.",
) -> AgentContext:
    return AgentContext(
        task_id="task-123",
        session_id="sess-abc",
        user_id="user-xyz",
        correlation_id="corr-001",
        stream_channel="channel-test",
        user_profile=profile or UserProfileSnapshot(),
        user_message=user_message,
    )


# ── SlotExtractor: _coerce ─────────────────────────────────────────────────


class TestCoerce:
    def test_string_fields_stripped(self):
        assert _coerce("target_role", "  Senior ML Engineer  ") == "Senior ML Engineer"

    def test_string_fields_empty_returns_none(self):
        assert _coerce("target_role", "   ") is None

    def test_list_field_from_list(self):
        assert _coerce("skills", ["Python", "SQL"]) == ["Python", "SQL"]

    def test_list_field_from_comma_string(self):
        assert _coerce("skills", "Python, SQL, React") == ["Python", "SQL", "React"]

    def test_list_field_from_semicolon_string(self):
        assert _coerce("constraints", "no relocation; limited budget") == [
            "no relocation",
            "limited budget",
        ]

    def test_list_field_empty_list_returns_none(self):
        assert _coerce("goals", []) is None

    def test_integer_field_from_int(self):
        assert _coerce("timeline_months", 12) == 12

    def test_integer_field_from_string_digits(self):
        assert _coerce("salary_goal", "120,000") == 120000

    def test_integer_field_zero_returns_none(self):
        assert _coerce("weekly_hours_available", 0) is None

    def test_none_value_returns_none(self):
        assert _coerce("target_role", None) is None


# ── SlotExtractor: _parse_llm_output ──────────────────────────────────────


class TestParseLlmOutput:
    def test_valid_response_parsed(self):
        raw = {
            "slots": [
                {
                    "field_name": "target_role",
                    "value": "ML Engineer",
                    "confidence": 0.95,
                    "source_span": "ML engineer",
                }
            ],
            "unresolved_mentions": ["startup environment"],
            "overall_confidence": 0.9,
        }
        result = _parse_llm_output(raw, "I want to be an ML engineer")
        assert len(result.slots) == 1
        assert result.slots[0].field_name == "target_role"
        assert result.slots[0].value == "ML Engineer"
        assert result.slots[0].confidence == 0.95
        assert result.unresolved_mentions == ["startup environment"]
        assert result.overall_confidence == 0.9

    def test_low_confidence_slot_excluded(self):
        raw = {
            "slots": [
                {
                    "field_name": "target_role",
                    "value": "ML Engineer",
                    "confidence": 0.5,
                    "source_span": "engineer",
                }
            ],
            "unresolved_mentions": [],
            "overall_confidence": 0.5,
        }
        result = _parse_llm_output(raw, "I might be an engineer")
        assert len(result.slots) == 0

    def test_unknown_field_name_excluded(self):
        raw = {
            "slots": [
                {
                    "field_name": "favourite_colour",
                    "value": "blue",
                    "confidence": 0.99,
                    "source_span": "blue",
                }
            ],
            "unresolved_mentions": [],
            "overall_confidence": 0.8,
        }
        result = _parse_llm_output(raw, "I like blue")
        assert len(result.slots) == 0

    def test_malformed_slot_entry_skipped(self):
        raw = {
            "slots": [{"no_field_name": True}, {"field_name": "target_role", "value": "Dev", "confidence": 0.9, "source_span": "Dev"}],
            "unresolved_mentions": [],
            "overall_confidence": 0.7,
        }
        result = _parse_llm_output(raw, "Dev")
        assert len(result.slots) == 1

    def test_empty_slots_list(self):
        raw = {"slots": [], "unresolved_mentions": [], "overall_confidence": 0.0}
        result = _parse_llm_output(raw, "Hello")
        assert result.slots == []
        assert result.overall_confidence == 0.0


# ── SlotExtractor: async extract() ────────────────────────────────────────


class TestSlotExtractorExtract:
    async def test_empty_text_returns_empty_result(self, extractor: SlotExtractor):
        result = await extractor.extract("   ")
        assert result.slots == []
        assert result.raw_text == "   "

    async def test_successful_extraction(
        self, extractor: SlotExtractor, mock_llm: AsyncMock
    ):
        payload = {
            "slots": [
                {
                    "field_name": "target_role",
                    "value": "ML Engineer",
                    "confidence": 0.95,
                    "source_span": "ML Engineer",
                },
                {
                    "field_name": "timeline_months",
                    "value": 12,
                    "confidence": 0.9,
                    "source_span": "12 months",
                },
            ],
            "unresolved_mentions": [],
            "overall_confidence": 0.92,
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))

        result = await extractor.extract("I want to be an ML Engineer in 12 months.")
        assert len(result.slots) == 2
        assert result.slots[0].field_name == "target_role"
        assert result.slots[1].field_name == "timeline_months"
        assert result.overall_confidence == 0.92

    async def test_llm_failure_returns_empty_result(
        self, extractor: SlotExtractor, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await extractor.extract("Some message", correlation_id="c1")
        assert result.slots == []
        assert result.raw_text == "Some message"

    async def test_llm_returns_invalid_json_returns_empty_result(
        self, extractor: SlotExtractor, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not json at all"))
        result = await extractor.extract("Some message")
        assert result.slots == []

    async def test_multiple_slot_types_extracted(
        self, extractor: SlotExtractor, mock_llm: AsyncMock
    ):
        payload = {
            "slots": [
                {"field_name": "skills", "value": ["Python", "SQL"], "confidence": 0.9, "source_span": "Python and SQL"},
                {"field_name": "location", "value": "Berlin", "confidence": 0.95, "source_span": "Berlin"},
                {"field_name": "salary_goal", "value": 120000, "confidence": 0.85, "source_span": "120k"},
            ],
            "unresolved_mentions": ["remote-friendly"],
            "overall_confidence": 0.9,
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await extractor.extract("I know Python and SQL. Based in Berlin. Want 120k.")
        assert {s.field_name for s in result.slots} == {"skills", "location", "salary_goal"}
        assert result.unresolved_mentions == ["remote-friendly"]


# ── ProfileBuilder helpers ─────────────────────────────────────────────────


class TestMergeList:
    def test_new_items_appended(self):
        assert _merge_list(["Python"], ["SQL", "React"]) == ["Python", "SQL", "React"]

    def test_duplicates_excluded(self):
        assert _merge_list(["Python"], ["Python", "SQL"]) == ["Python", "SQL"]

    def test_case_insensitive_dedup(self):
        assert _merge_list(["python"], ["Python", "SQL"]) == ["python", "SQL"]

    def test_existing_none(self):
        assert _merge_list(None, ["Python"]) == ["Python"]

    def test_new_none(self):
        assert _merge_list(["Python"], None) == ["Python"]

    def test_both_none(self):
        assert _merge_list(None, None) == []


class TestCompletenessScore:
    def test_empty_profile_scores_zero(self, empty_profile: UserProfileSnapshot):
        assert completeness_score(empty_profile) == 0.0

    def test_full_profile_scores_one(self, full_profile: UserProfileSnapshot):
        assert completeness_score(full_profile) == 1.0

    def test_target_role_only_scores_thirty_pct(self):
        profile = UserProfileSnapshot(target_role="ML Engineer")
        assert completeness_score(profile) == pytest.approx(0.30, abs=0.001)


class TestMissingSlots:
    def test_all_missing_from_empty_profile(self, empty_profile: UserProfileSnapshot):
        slots = missing_slots(empty_profile)
        assert "target_role" in slots
        assert slots[0] == "target_role"  # highest weight first

    def test_no_missing_from_full_profile(self, full_profile: UserProfileSnapshot):
        assert missing_slots(full_profile) == []

    def test_partial_profile_missing_slots(self, partial_profile: UserProfileSnapshot):
        slots = missing_slots(partial_profile)
        assert "target_role" not in slots
        assert "location" in slots


# ── ProfileBuilder.build() ─────────────────────────────────────────────────


class TestProfileBuilderBuild:
    def test_empty_profile_gets_new_fields(
        self, builder: ProfileBuilder, empty_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[
                ExtractedSlot("target_role", "ML Engineer", 0.9, "ML Engineer"),
                ExtractedSlot("timeline_months", 12, 0.85, "12 months"),
            ],
        )
        updated, diff = builder.build(empty_profile, extraction)
        assert updated.target_role == "ML Engineer"
        assert updated.timeline_months == 12
        assert "target_role" in diff.added_fields
        assert "timeline_months" in diff.added_fields
        assert diff.old_completeness == 0.0
        assert diff.new_completeness > 0.0

    def test_existing_skill_merged_not_replaced(
        self, builder: ProfileBuilder, partial_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[ExtractedSlot("skills", ["React", "SQL"], 0.9, "React and SQL")],
        )
        updated, diff = builder.build(partial_profile, extraction)
        # SQL was already in partial_profile; React is new
        assert "Python" in updated.skills
        assert "SQL" in updated.skills
        assert "React" in updated.skills
        assert updated.skills.count("SQL") == 1  # no duplicates

    def test_scalar_field_overwritten(
        self, builder: ProfileBuilder, partial_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[ExtractedSlot("target_role", "Staff Engineer", 0.95, "Staff Engineer")],
        )
        updated, diff = builder.build(partial_profile, extraction)
        assert updated.target_role == "Staff Engineer"
        assert "target_role" in diff.updated_fields

    def test_no_change_when_value_unchanged(
        self, builder: ProfileBuilder, partial_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[ExtractedSlot("target_role", "Senior ML Engineer", 0.9, "Senior ML Engineer")],
        )
        updated, diff = builder.build(partial_profile, extraction)
        assert "target_role" in diff.unchanged_fields
        assert updated.target_role == partial_profile.target_role

    def test_empty_extraction_returns_original_profile(
        self, builder: ProfileBuilder, partial_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(raw_text="nothing here")
        updated, diff = builder.build(partial_profile, extraction)
        assert updated == partial_profile
        assert diff.added_fields == []
        assert diff.updated_fields == []

    def test_goals_and_constraints_merged(
        self, builder: ProfileBuilder, empty_profile: UserProfileSnapshot
    ):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[
                ExtractedSlot("goals", ["lead a team", "build ML products"], 0.8, "lead a team and build ML products"),
                ExtractedSlot("constraints", ["no relocation"], 0.75, "no relocation"),
            ],
        )
        updated, diff = builder.build(empty_profile, extraction)
        assert updated.goals == ["lead a team", "build ML products"]
        assert updated.constraints == ["no relocation"]


# ── IntakeAgent ────────────────────────────────────────────────────────────


class TestIntakeAgent:
    def _make_agent(
        self,
        extraction: SlotExtractionResult | None = None,
        diff: ProfileDiff | None = None,
        emit_events: bool = False,
    ) -> tuple[IntakeAgent, AsyncMock, MagicMock]:
        mock_extractor = AsyncMock(spec=SlotExtractor)
        mock_builder = MagicMock(spec=ProfileBuilder)
        mock_publisher = MagicMock() if emit_events else None

        _extraction = extraction or SlotExtractionResult(raw_text="test")
        _diff = diff or ProfileDiff(
            added_fields=["target_role"],
            updated_fields=[],
            unchanged_fields=[],
            old_completeness=0.0,
            new_completeness=0.30,
        )

        mock_extractor.extract = AsyncMock(return_value=_extraction)
        mock_builder.build = MagicMock(
            return_value=(UserProfileSnapshot(target_role="ML Engineer"), _diff)
        )

        agent = IntakeAgent(
            slot_extractor=mock_extractor,
            profile_builder=mock_builder,
            event_publisher=mock_publisher,
        )
        return agent, mock_extractor, mock_builder

    def test_agent_type(self):
        agent, _, _ = self._make_agent()
        assert agent.agent_type == AgentType.INTAKE

    def test_display_name(self):
        agent, _, _ = self._make_agent()
        assert agent.display_name == "Intake & Profile Agent"

    async def test_execute_returns_correct_keys(self):
        agent, mock_extractor, _ = self._make_agent()
        context = _make_context()
        result = await agent._execute(context)

        required_keys = {
            "user_profile",
            "completeness_score",
            "missing_slots",
            "needs_clarification",
            "extracted_slots",
            "unresolved_mentions",
            "diff",
        }
        assert required_keys.issubset(result.keys())

    async def test_execute_passes_user_message_to_extractor(self):
        agent, mock_extractor, _ = self._make_agent()
        context = _make_context(user_message="I am a Python dev")
        await agent._execute(context)
        mock_extractor.extract.assert_called_once()
        call_args = mock_extractor.extract.call_args
        assert call_args[0][0] == "I am a Python dev"

    async def test_execute_passes_profile_and_extraction_to_builder(self):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[ExtractedSlot("target_role", "ML Engineer", 0.9, "ML Engineer")],
        )
        agent, mock_extractor, mock_builder = self._make_agent(extraction=extraction)
        mock_extractor.extract = AsyncMock(return_value=extraction)
        profile = UserProfileSnapshot(current_role="Dev")
        context = _make_context(profile=profile)
        await agent._execute(context)

        mock_builder.build.assert_called_once()
        build_args = mock_builder.build.call_args
        assert build_args[0][0] == profile
        assert build_args[0][1] == extraction

    async def test_needs_clarification_true_when_below_threshold(self):
        diff = ProfileDiff(
            added_fields=["target_role"],
            updated_fields=[],
            unchanged_fields=[],
            old_completeness=0.0,
            new_completeness=0.30,  # below 0.75
        )
        agent, _, _ = self._make_agent(diff=diff)
        # Builder returns a profile with only target_role set → missing_slots is non-empty
        context = _make_context()
        result = await agent._execute(context)
        assert result["needs_clarification"] is True

    async def test_needs_clarification_false_when_above_threshold(self):
        diff = ProfileDiff(
            added_fields=list(
                ["target_role", "current_role", "skills", "location", "timeline_months", "weekly_hours_available", "salary_goal"]
            ),
            updated_fields=[],
            unchanged_fields=[],
            old_completeness=0.0,
            new_completeness=1.0,
        )

        mock_extractor = AsyncMock(spec=SlotExtractor)
        mock_builder = MagicMock(spec=ProfileBuilder)
        full = UserProfileSnapshot(
            target_role="ML Engineer",
            current_role="Dev",
            skills=["Python"],
            location="Berlin",
            timeline_months=12,
            weekly_hours_available=10,
            salary_goal=100_000,
        )
        mock_extractor.extract = AsyncMock(return_value=SlotExtractionResult(raw_text=""))
        mock_builder.build = MagicMock(return_value=(full, diff))

        agent = IntakeAgent(slot_extractor=mock_extractor, profile_builder=mock_builder)
        context = _make_context()
        result = await agent._execute(context)
        assert result["needs_clarification"] is False

    async def test_progress_events_emitted_when_publisher_present(self):
        mock_publisher = MagicMock()
        mock_extractor = AsyncMock(spec=SlotExtractor)
        mock_builder = MagicMock(spec=ProfileBuilder)
        mock_extractor.extract = AsyncMock(
            return_value=SlotExtractionResult(raw_text="test")
        )
        mock_builder.build = MagicMock(
            return_value=(
                UserProfileSnapshot(),
                ProfileDiff([], [], [], 0.0, 0.0),
            )
        )

        agent = IntakeAgent(
            slot_extractor=mock_extractor,
            profile_builder=mock_builder,
            event_publisher=mock_publisher,
        )
        context = _make_context()
        await agent._execute(context)

        assert mock_publisher.emit.call_count == 3  # one per pipeline step

    async def test_no_progress_events_without_publisher(self):
        agent, _, _ = self._make_agent(emit_events=False)
        context = _make_context()
        # Should not raise even without a publisher
        result = await agent._execute(context)
        assert "completeness_score" in result

    async def test_empty_user_message_handled_gracefully(self):
        agent, mock_extractor, _ = self._make_agent()
        context = _make_context(user_message="")
        await agent._execute(context)
        mock_extractor.extract.assert_called_once_with("", correlation_id="corr-001")

    async def test_extracted_slots_in_output(self):
        extraction = SlotExtractionResult(
            raw_text="test",
            slots=[
                ExtractedSlot("target_role", "ML Engineer", 0.95, "ML Engineer"),
            ],
        )
        agent, mock_extractor, _ = self._make_agent(extraction=extraction)
        mock_extractor.extract = AsyncMock(return_value=extraction)
        context = _make_context()
        result = await agent._execute(context)

        assert len(result["extracted_slots"]) == 1
        slot_out = result["extracted_slots"][0]
        assert slot_out["field_name"] == "target_role"
        assert slot_out["confidence"] == 0.95

    async def test_full_pipeline_via_base_agent_run(self):
        """Verify the public run() wrapper returns a well-formed AgentResult."""
        from agents.contracts.results import AgentResultStatus

        agent, _, _ = self._make_agent()
        context = _make_context()
        agent_result = await agent.run(context)

        assert agent_result.agent_type == AgentType.INTAKE.value
        assert agent_result.status == AgentResultStatus.COMPLETED
        assert "user_profile" in agent_result.output
        assert agent_result.duration_ms >= 0
