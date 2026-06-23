"""Unit tests for the cross-bus contract types (``agents.contracts``).

These Pydantic models are the wire format between the API and the agent workers.
Their defaults, validation bounds, and enum values are a hard contract — both
sides serialise/deserialise against them without importing each other.
"""
import pytest
from pydantic import ValidationError

from agents.contracts.results import (
    AgentResult,
    AgentResultStatus,
    OrchestratorResult,
)
from agents.contracts.tasks import (
    AgentTaskInput,
    AgentType,
    OrchestratorTaskInput,
    TaskPriority,
    UserProfileSnapshot,
)

pytestmark = pytest.mark.unit


# ── AgentResult ─────────────────────────────────────────────────────────────────


def test_agent_result_minimal_defaults() -> None:
    r = AgentResult(task_id="t1", agent_type="coach", status=AgentResultStatus.COMPLETED)
    assert r.output == {}
    assert r.confidence == 1.0
    assert r.citations == []
    assert r.error_message is None
    assert r.duration_ms == 0


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_agent_result_confidence_must_be_within_unit_interval(bad: float) -> None:
    with pytest.raises(ValidationError):
        AgentResult(
            task_id="t1", agent_type="coach", status=AgentResultStatus.COMPLETED, confidence=bad
        )


def test_agent_result_status_enum_values() -> None:
    assert AgentResultStatus.COMPLETED.value == "completed"
    assert {s.value for s in AgentResultStatus} == {"completed", "failed", "partial", "timeout"}


# ── OrchestratorResult ──────────────────────────────────────────────────────────


def test_orchestrator_result_defaults() -> None:
    r = OrchestratorResult(
        request_id="r1", session_id="s1", user_id="u1", status=AgentResultStatus.COMPLETED
    )
    assert r.agent_results == {}
    assert r.validation_passed is True
    assert r.clarification_required is False
    assert r.clarification_questions == []
    assert r.roadmap is None


# ── Task inputs ─────────────────────────────────────────────────────────────────


def test_agent_task_input_autogenerates_ids() -> None:
    t = AgentTaskInput(
        agent_type=AgentType.INTAKE,
        session_id="s1",
        user_id="u1",
        user_profile=UserProfileSnapshot(),
    )
    assert t.task_id  # uuid generated
    assert t.correlation_id
    assert t.task_id != t.correlation_id
    assert t.priority is TaskPriority.NORMAL


def test_agent_type_enum_covers_all_specialists() -> None:
    assert {t.value for t in AgentType} == {
        "intake",
        "cv_analysis",
        "gap_analysis",
        "market_intelligence",
        "roadmap_generation",
        "validator",
        "learning_resources",
        "networking",
        "opportunity",
        "progress",
        "coach",
    }


def test_orchestrator_task_input_round_defaults_to_zero() -> None:
    t = OrchestratorTaskInput(
        session_id="s1",
        user_id="u1",
        user_message="help me",
        user_profile=UserProfileSnapshot(),
        stream_channel="chan:1",
    )
    assert t.clarification_round == 0
    assert t.previous_clarification_questions == []
    assert t.forced_intent is None


def test_orchestrator_task_input_rejects_negative_round() -> None:
    with pytest.raises(ValidationError):
        OrchestratorTaskInput(
            session_id="s1",
            user_id="u1",
            user_message="hi",
            user_profile=UserProfileSnapshot(),
            stream_channel="c",
            clarification_round=-1,
        )
