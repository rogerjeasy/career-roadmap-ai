"""Regression tests pinning agent-contract invariants.

Failures the wire format must never silently reintroduce: an error result that
still carries an out-of-range confidence, or a task envelope that loses its
correlation id when serialised.
"""
import pytest
from pydantic import ValidationError

from agents.contracts.results import AgentResult, AgentResultStatus, OrchestratorResult
from agents.contracts.tasks import AgentTaskInput, AgentType, UserProfileSnapshot

pytestmark = pytest.mark.regression


def test_confidence_above_one_is_rejected_not_clamped() -> None:
    # REGRESSION: confidence is a *bounded* float — callers must not be able to
    # ship 1.5 and have it silently pass downstream consumers.
    with pytest.raises(ValidationError):
        AgentResult(
            task_id="t",
            agent_type="coach",
            status=AgentResultStatus.FAILED,
            confidence=1.5,
        )


def test_failed_result_keeps_error_message_through_serialisation() -> None:
    # REGRESSION: failures cross the bus as AgentResult(status=FAILED) with an
    # error_message — that field must survive a JSON roundtrip.
    r = AgentResult(
        task_id="t",
        agent_type="coach",
        status=AgentResultStatus.FAILED,
        error_message="LLM provider unavailable",
    )
    rebuilt = AgentResult.model_validate(r.model_dump(mode="json"))
    assert rebuilt.status is AgentResultStatus.FAILED
    assert rebuilt.error_message == "LLM provider unavailable"


def test_correlation_id_survives_roundtrip() -> None:
    # REGRESSION: correlation_id ties all sub-tasks of one request together; it
    # must not be regenerated/dropped when the envelope is rebuilt on the worker.
    t = AgentTaskInput(
        agent_type=AgentType.INTAKE,
        session_id="s",
        user_id="u",
        user_profile=UserProfileSnapshot(),
    )
    rebuilt = AgentTaskInput.model_validate(t.model_dump(mode="json"))
    assert rebuilt.correlation_id == t.correlation_id
    assert rebuilt.task_id == t.task_id


def test_orchestrator_result_clarification_questions_default_is_isolated() -> None:
    # REGRESSION: default_factory list must not be shared between instances.
    a = OrchestratorResult(
        request_id="r1", session_id="s", user_id="u", status=AgentResultStatus.PARTIAL
    )
    b = OrchestratorResult(
        request_id="r2", session_id="s", user_id="u", status=AgentResultStatus.PARTIAL
    )
    a.clarification_questions.append({"q": "?"})
    assert b.clarification_questions == []
