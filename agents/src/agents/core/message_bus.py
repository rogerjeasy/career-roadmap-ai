"""MessageBus — abstract interface for inter-agent communication.

Concrete implementations live in ``agents.bus``. This module exposes the
Protocol so that code that only needs to *type-hint* against the bus
doesn't have to import Celery or Redis.
"""
from typing import Any, Protocol, runtime_checkable

from agents.contracts.events import AgentEvent
from agents.contracts.tasks import AgentTaskInput, OrchestratorTaskInput


@runtime_checkable
class TaskPublisherProtocol(Protocol):
    """Publishes tasks to the async task queue."""

    def dispatch_orchestration(self, task_input: OrchestratorTaskInput) -> str:
        """Enqueue a top-level orchestration request. Returns the task ID."""
        ...

    def dispatch_agent(self, task_input: AgentTaskInput) -> str:
        """Enqueue a single specialist-agent task. Returns the task ID."""
        ...


@runtime_checkable
class EventPublisherProtocol(Protocol):
    """Publishes AgentEvents to the real-time event channel."""

    def emit(self, event: AgentEvent) -> None:
        """Publish an event. Best-effort — must not raise on failure."""
        ...


@runtime_checkable
class MessageBusProtocol(Protocol):
    """Composite interface — exposes both task and event publishing."""

    @property
    def tasks(self) -> TaskPublisherProtocol: ...

    @property
    def events(self) -> EventPublisherProtocol: ...

    def health_check(self) -> dict[str, Any]: ...
