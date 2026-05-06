"""Tests for the CoachAgent.

Covers:
  - CoachContextAssembler: context extraction from profile additional fields
  - _build_user_prompt: prompt structure
  - _validate_llm_output: JSON parsing and coercion
  - _fallback_response: deterministic fallback content
  - CoachAgent._execute: full pipeline, progress events, LLM failure fallback
  - CoachAgent via BaseAgent.run(): well-formed AgentResult

All LLM calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.coach.coach_agent import (
    CoachAgent,
    _build_user_prompt,
    _fallback_response,
    _validate_llm_output,
)
from agents.coach.context_assembler import CoachContextAssembler
from agents.coach.models import CoachContextBundle, CoachingType


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_profile(
    *,
    target_role: str | None = "Senior ML Engineer",
    current_role: str | None = "Backend Developer",
    skills: list | None = None,
    timeline_months: int | None = 12,
    conversation_history: list | None = None,
    plan_context: dict | None = None,
) -> UserProfileSnapshot:
    additional: dict = {}
    if conversation_history is not None:
        additional["conversation_history"] = conversation_history
    if plan_context is not None:
        additional["plan_context"] = plan_context

    return UserProfileSnapshot(
        target_role=target_role,
        current_role=current_role,
        skills=skills or ["Python", "SQL"],
        goals=["Lead ML team"],
        timeline_months=timeline_months,
        additional=additional,
    )


def _make_context(
    *,
    user_message: str = "How should I prepare for ML engineer interviews?",
    profile: UserProfileSnapshot | None = None,
    plan_snapshot: dict | None = None,
) -> AgentContext:
    return AgentContext(
        task_id="task-coach-001",
        session_id="sess-coach",
        user_id="user-coach",
        correlation_id="corr-coach",
        stream_channel="channel-coach",
        user_profile=profile or _make_profile(),
        user_message=user_message,
        plan_snapshot=plan_snapshot or {},
    )


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _valid_llm_payload(coaching_type: str = "interview_prep") -> dict:
    return {
        "response": "## Interview Prep\n\nHere are key areas to focus on...",
        "coaching_type": coaching_type,
        "confidence": 0.88,
        "follow_up_suggestions": ["What frameworks should I practice?", "How long for LeetCode?"],
        "timeline_concern": False,
        "timeline_note": None,
        "actionable_steps": [
            {"step": "Practice 3 LeetCode mediums daily", "timeframe": "this week", "priority": "high"},
        ],
        "assumptions": ["User is aiming for FAANG-level roles"],
    }


# ── CoachContextAssembler ──────────────────────────────────────────────────────


class TestCoachContextAssembler:
    def setup_method(self):
        self.assembler = CoachContextAssembler()

    def test_basic_profile_fields_extracted(self):
        ctx = _make_context()
        bundle = self.assembler.assemble(ctx)
        assert bundle.target_role == "Senior ML Engineer"
        assert bundle.current_role == "Backend Developer"
        assert "Python" in bundle.skills
        assert bundle.timeline_months == 12

    def test_conversation_history_extracted_from_additional(self):
        history = [
            {"role": "user", "content": "What is ML?"},
            {"role": "assistant", "content": "ML is..."},
        ]
        profile = _make_profile(conversation_history=history)
        ctx = _make_context(profile=profile)
        bundle = self.assembler.assemble(ctx)
        assert len(bundle.conversation_history) == 2
        assert bundle.conversation_history[0]["role"] == "user"

    def test_invalid_history_entries_ignored(self):
        bad_history = [{"no_role": "oops"}, {"role": "user", "content": "valid"}]
        profile = _make_profile(conversation_history=bad_history)
        ctx = _make_context(profile=profile)
        bundle = self.assembler.assemble(ctx)
        assert len(bundle.conversation_history) == 1

    def test_plan_context_produces_roadmap_summary(self):
        plan_ctx = {"roadmap_id": "road-001", "snapshot": {"phases": 3}}
        profile = _make_profile(plan_context=plan_ctx)
        ctx = _make_context(profile=profile)
        bundle = self.assembler.assemble(ctx)
        assert bundle.roadmap_summary is not None
        assert "road-001" in bundle.roadmap_summary

    def test_live_plan_snapshot_roadmap_summary(self):
        plan_snapshot = {
            "roadmap_generation": {
                "phases": [
                    {"name": "Foundation"},
                    {"name": "Specialisation"},
                ],
                "total_weeks": 24,
            }
        }
        ctx = _make_context(plan_snapshot=plan_snapshot)
        bundle = self.assembler.assemble(ctx)
        assert bundle.has_plan is True
        assert "Foundation" in bundle.roadmap_summary
        assert "24 weeks" in bundle.roadmap_summary

    def test_gap_summary_extracted_from_plan_snapshot(self):
        plan_snapshot = {
            "gap_analysis": {
                "diff_score": 0.45,
                "critical_gaps": ["PyTorch", "MLOps"],
                "priority_order": ["PyTorch", "MLOps", "System Design"],
            }
        }
        ctx = _make_context(plan_snapshot=plan_snapshot)
        bundle = self.assembler.assemble(ctx)
        assert bundle.gap_summary is not None
        assert "PyTorch" in bundle.gap_summary

    def test_no_plan_has_plan_false(self):
        ctx = _make_context()
        bundle = self.assembler.assemble(ctx)
        assert bundle.has_plan is False

    def test_history_capped_at_max_turns(self):
        long_history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        profile = _make_profile(conversation_history=long_history)
        ctx = _make_context(profile=profile)
        bundle = self.assembler.assemble(ctx)
        assert len(bundle.conversation_history) <= 12


# ── _build_user_prompt ────────────────────────────────────────────────────────


class TestBuildUserPrompt:
    def _make_bundle(self, **kwargs) -> CoachContextBundle:
        defaults = dict(
            user_message="How do I prepare?",
            current_role="Dev",
            target_role="ML Engineer",
            skills=["Python"],
            timeline_months=12,
        )
        defaults.update(kwargs)
        return CoachContextBundle(**defaults)

    def test_contains_user_message(self):
        bundle = self._make_bundle(user_message="Tell me about interviews")
        prompt = _build_user_prompt(bundle)
        assert "Tell me about interviews" in prompt

    def test_contains_profile_fields(self):
        bundle = self._make_bundle()
        prompt = _build_user_prompt(bundle)
        assert "Dev" in prompt
        assert "ML Engineer" in prompt
        assert "Python" in prompt
        assert "12 months" in prompt

    def test_roadmap_section_present_when_has_plan(self):
        bundle = self._make_bundle(has_plan=True, roadmap_summary="2-phase plan, 20 weeks")
        prompt = _build_user_prompt(bundle)
        assert "ROADMAP CONTEXT" in prompt
        assert "2-phase plan" in prompt

    def test_roadmap_section_absent_when_no_plan(self):
        bundle = self._make_bundle(has_plan=False)
        prompt = _build_user_prompt(bundle)
        assert "ROADMAP CONTEXT" not in prompt

    def test_conversation_history_included(self):
        history = [{"role": "user", "content": "Earlier question"}, {"role": "assistant", "content": "Earlier answer"}]
        bundle = self._make_bundle(conversation_history=history)
        prompt = _build_user_prompt(bundle)
        assert "CONVERSATION HISTORY" in prompt
        assert "Earlier question" in prompt


# ── _validate_llm_output ──────────────────────────────────────────────────────


class TestValidateLlmOutput:
    def test_valid_full_payload(self):
        result = _validate_llm_output(_valid_llm_payload())
        assert result.coaching_type == CoachingType.INTERVIEW_PREP
        assert result.confidence == pytest.approx(0.88)
        assert len(result.follow_up_suggestions) == 2
        assert result.timeline_concern is False
        assert len(result.actionable_steps) == 1

    def test_invalid_coaching_type_falls_back_to_ad_hoc(self):
        payload = _valid_llm_payload()
        payload["coaching_type"] = "not_a_real_type"
        result = _validate_llm_output(payload)
        assert result.coaching_type == CoachingType.AD_HOC

    def test_missing_response_key_returns_fallback_text(self):
        result = _validate_llm_output({})
        assert "No response generated" in result.response

    def test_timeline_concern_true_sets_note(self):
        payload = _valid_llm_payload()
        payload["timeline_concern"] = True
        payload["timeline_note"] = "12 months is unrealistic; aim for 18."
        result = _validate_llm_output(payload)
        assert result.timeline_concern is True
        assert result.timeline_note == "12 months is unrealistic; aim for 18."

    def test_malformed_actionable_steps_skipped(self):
        payload = _valid_llm_payload()
        payload["actionable_steps"] = ["not a dict", {"step": "ok", "timeframe": "now", "priority": "high"}]
        result = _validate_llm_output(payload)
        assert len(result.actionable_steps) == 1

    def test_assumptions_list_extracted(self):
        payload = _valid_llm_payload()
        payload["assumptions"] = ["user is senior", "target is EU market"]
        result = _validate_llm_output(payload)
        assert "user is senior" in result.assumptions


# ── _fallback_response ────────────────────────────────────────────────────────


class TestFallbackResponse:
    def test_fallback_contains_user_message(self):
        bundle = CoachContextBundle(user_message="What should I study?")
        result = _fallback_response(bundle)
        assert "What should I study?" in result.response

    def test_fallback_confidence_is_low(self):
        bundle = CoachContextBundle(user_message="test")
        result = _fallback_response(bundle)
        assert result.confidence <= 0.2

    def test_fallback_has_assumption(self):
        bundle = CoachContextBundle(user_message="test")
        result = _fallback_response(bundle)
        assert len(result.assumptions) > 0


# ── CoachAgent ────────────────────────────────────────────────────────────────


class TestCoachAgent:
    def _make_agent(
        self,
        llm_payload: dict | None = None,
        llm_raises: Exception | None = None,
        emit_events: bool = False,
    ) -> tuple[CoachAgent, MagicMock | None]:
        mock_llm = AsyncMock()
        mock_publisher = MagicMock() if emit_events else None

        if llm_raises:
            mock_llm.ainvoke = AsyncMock(side_effect=llm_raises)
        else:
            payload = llm_payload or _valid_llm_payload()
            mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))

        agent = CoachAgent(event_publisher=mock_publisher, llm=mock_llm)
        return agent, mock_publisher

    def test_agent_type(self):
        agent, _ = self._make_agent()
        assert agent.agent_type == AgentType.COACH

    def test_display_name(self):
        agent, _ = self._make_agent()
        assert agent.display_name == "Career Coach"

    async def test_execute_returns_required_keys(self):
        agent, _ = self._make_agent()
        ctx = _make_context()
        result = await agent._execute(ctx)
        assert "response" in result
        assert "coaching_type" in result
        assert "confidence" in result
        assert "follow_up_suggestions" in result
        assert "timeline_concern" in result

    async def test_execute_passes_user_message_to_llm(self):
        agent, _ = self._make_agent()
        ctx = _make_context(user_message="Should I quit my job now?")
        await agent._execute(ctx)
        call_args = agent._llm.ainvoke.call_args
        prompt_text = str(call_args[0][0])  # message list as string
        assert "Should I quit my job now?" in prompt_text

    async def test_llm_failure_returns_fallback_response(self):
        agent, _ = self._make_agent(llm_raises=RuntimeError("LLM unavailable"))
        ctx = _make_context()
        result = await agent._execute(ctx)
        assert result["confidence"] <= 0.2
        assert result["response"]

    async def test_timeline_concern_surfaced_in_output(self):
        payload = _valid_llm_payload()
        payload["timeline_concern"] = True
        payload["timeline_note"] = "This timeline is not realistic."
        agent, _ = self._make_agent(llm_payload=payload)
        ctx = _make_context(user_message="I want to become CTO in 3 months")
        result = await agent._execute(ctx)
        assert result["timeline_concern"] is True
        assert result["timeline_note"] is not None

    async def test_progress_events_emitted_when_publisher_present(self):
        agent, mock_publisher = self._make_agent(emit_events=True)
        ctx = _make_context()
        await agent._execute(ctx)
        assert mock_publisher.emit.call_count >= 2  # context_assembly + llm_inference

    async def test_no_progress_events_without_publisher(self):
        agent, _ = self._make_agent(emit_events=False)
        ctx = _make_context()
        result = await agent._execute(ctx)
        assert "response" in result

    async def test_markdown_code_fence_stripped_from_llm_response(self):
        payload = _valid_llm_payload()
        fenced = f"```json\n{json.dumps(payload)}\n```"
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(fenced))
        agent = CoachAgent(llm=mock_llm)
        ctx = _make_context()
        result = await agent._execute(ctx)
        assert result["coaching_type"] == "interview_prep"

    async def test_full_pipeline_via_base_agent_run(self):
        agent, _ = self._make_agent()
        ctx = _make_context()
        agent_result = await agent.run(ctx)
        assert agent_result.agent_type == AgentType.COACH.value
        assert agent_result.status == AgentResultStatus.COMPLETED
        assert "response" in agent_result.output
        assert agent_result.duration_ms >= 0

    async def test_rich_context_with_plan_snapshot(self):
        plan_snapshot = {
            "roadmap_generation": {"phases": [{"name": "Foundation"}], "total_weeks": 16},
            "gap_analysis": {"diff_score": 0.6, "critical_gaps": ["PyTorch"]},
        }
        agent, _ = self._make_agent()
        ctx = _make_context(plan_snapshot=plan_snapshot)
        result = await agent._execute(ctx)
        assert "response" in result

    async def test_interview_prep_classified_correctly(self):
        payload = _valid_llm_payload(coaching_type="interview_prep")
        agent, _ = self._make_agent(llm_payload=payload)
        ctx = _make_context(user_message="What interview questions will I face?")
        result = await agent._execute(ctx)
        assert result["coaching_type"] == "interview_prep"
