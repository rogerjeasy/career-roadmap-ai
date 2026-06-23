"""Integration tests: contract serialisation across the (simulated) bus boundary.

Celery/Redis carry these objects as JSON. These tests assert that a fully
populated object survives ``model_dump(mode="json")`` → ``model_validate`` with
no loss — the exact path the API and workers rely on.
"""
import json

import pytest

from agents.contracts.results import AgentResult, AgentResultStatus, OrchestratorResult
from agents.contracts.tasks import (
    AgentTaskInput,
    AgentType,
    TaskPriority,
    UserProfileSnapshot,
)

pytestmark = pytest.mark.integration


def test_orchestrator_result_json_roundtrip_with_nested_agent_results() -> None:
    original = OrchestratorResult(
        request_id="r1",
        session_id="s1",
        user_id="u1",
        status=AgentResultStatus.COMPLETED,
        roadmap={"phases": [{"week": 1}]},
        roadmap_id="rm-1",
        agent_results={
            "roadmap_generation": AgentResult(
                task_id="t1",
                agent_type="roadmap_generation",
                status=AgentResultStatus.COMPLETED,
                output={"phases": 12},
                confidence=0.82,
                citations=["src://kb/1"],
                duration_ms=4200,
            )
        },
        confidence=0.82,
        duration_ms=9000,
    )

    # Serialise the way Celery would, then rebuild on the worker/API side.
    wire = json.dumps(original.model_dump(mode="json"))
    rebuilt = OrchestratorResult.model_validate(json.loads(wire))

    assert rebuilt == original
    assert rebuilt.agent_results["roadmap_generation"].confidence == 0.82
    assert rebuilt.status is AgentResultStatus.COMPLETED


def test_agent_task_input_json_roundtrip_preserves_enums_and_ids() -> None:
    original = AgentTaskInput(
        agent_type=AgentType.MARKET_INTELLIGENCE,
        session_id="s1",
        user_id="u1",
        priority=TaskPriority.HIGH,
        user_profile=UserProfileSnapshot(target_role="PM", skills=["sql", "python"]),
        payload={"query": "salary"},
        correlation_id="corr-1",
    )

    wire = json.dumps(original.model_dump(mode="json"))
    rebuilt = AgentTaskInput.model_validate(json.loads(wire))

    assert rebuilt.agent_type is AgentType.MARKET_INTELLIGENCE
    assert rebuilt.priority is TaskPriority.HIGH
    assert rebuilt.user_profile.skills == ["sql", "python"]
    assert rebuilt.correlation_id == "corr-1"
    assert rebuilt.task_id == original.task_id
