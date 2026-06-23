"""Unit tests for the agent framework exception hierarchy (``agents.core.exceptions``)."""
import pytest

from agents.core.exceptions import (
    AgentConfigurationError,
    AgentError,
    AgentTimeoutError,
    AgentValidationError,
    BusError,
    BusPublishError,
    BusSubscribeError,
    ClarificationError,
    OrchestratorError,
    PlanningError,
    SynthesisError,
)

pytestmark = pytest.mark.unit


def test_agent_error_carries_agent_type() -> None:
    exc = AgentError("boom", agent_type="coach")
    assert exc.agent_type == "coach"
    assert str(exc) == "boom"


def test_agent_error_agent_type_optional() -> None:
    assert AgentError("boom").agent_type is None


@pytest.mark.parametrize(
    "exc_cls",
    [AgentConfigurationError, AgentTimeoutError, AgentValidationError],
)
def test_agent_subclasses(exc_cls: type[AgentError]) -> None:
    assert issubclass(exc_cls, AgentError)
    assert exc_cls("x", agent_type="t").agent_type == "t"


@pytest.mark.parametrize("exc_cls", [BusPublishError, BusSubscribeError])
def test_bus_subclasses(exc_cls: type[BusError]) -> None:
    assert issubclass(exc_cls, BusError)


@pytest.mark.parametrize("exc_cls", [PlanningError, ClarificationError, SynthesisError])
def test_orchestrator_subclasses(exc_cls: type[OrchestratorError]) -> None:
    assert issubclass(exc_cls, OrchestratorError)


def test_distinct_hierarchies_do_not_overlap() -> None:
    assert not issubclass(BusError, AgentError)
    assert not issubclass(OrchestratorError, AgentError)
