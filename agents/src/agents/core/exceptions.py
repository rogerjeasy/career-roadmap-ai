"""Agent framework exception hierarchy.

All exceptions are framework-internal. Failures that cross the bus boundary
are expressed as ``AgentResult(status=FAILED)`` or ``OrchestratorResult``
with an ``error_message`` — never by propagating Python exceptions over the wire.
"""


class AgentError(Exception):
    """Base for all agent-framework errors."""

    def __init__(self, message: str, agent_type: str | None = None) -> None:
        self.agent_type = agent_type
        super().__init__(message)


class AgentConfigurationError(AgentError):
    """Agent is misconfigured — unrecoverable at runtime."""


class AgentTimeoutError(AgentError):
    """Agent exceeded its allocated time budget."""


class AgentValidationError(AgentError):
    """Agent input or output failed schema validation."""


class BusError(Exception):
    """Message bus infrastructure failure."""


class BusPublishError(BusError):
    """Failed to publish a task or event to the broker."""


class BusSubscribeError(BusError):
    """Failed to subscribe to a pub/sub channel."""


class OrchestratorError(Exception):
    """Master orchestrator logic failure."""


class PlanningError(OrchestratorError):
    """Task planner failed to build a valid execution DAG."""


class ClarificationError(OrchestratorError):
    """Clarification engine failed to score or generate questions."""


class SynthesisError(OrchestratorError):
    """Result aggregator failed to synthesise agent outputs."""
