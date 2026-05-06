"""Agent event types — emitted to Redis pub/sub during orchestration.

The API layer subscribes to a per-session channel and forwards these
events to the browser client via SSE. Every field is JSON-serialisable
so the event can cross the Redis wire without any transformation.
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentEventType(str, Enum):
    # Orchestration lifecycle
    ORCHESTRATION_STARTED = "orchestration_started"
    ORCHESTRATION_COMPLETED = "orchestration_completed"
    ORCHESTRATION_FAILED = "orchestration_failed"

    # Specialist agent lifecycle
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # Clarification flow
    CLARIFICATION_REQUIRED = "clarification_required"
    CLARIFICATION_RESOLVED = "clarification_resolved"

    # LLM token streaming
    STREAM_TOKEN = "stream_token"
    STREAM_DONE = "stream_done"

    # Fine-grained progress
    STEP_PROGRESS = "step_progress"


class AgentEvent(BaseModel):
    """An event published to Redis pub/sub during an orchestration run.

    ``correlation_id`` matches ``OrchestratorTaskInput.request_id`` so the
    API can route events belonging to the same generation request.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: AgentEventType
    session_id: str
    user_id: str
    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse_data(self) -> str:
        """Return a JSON string ready to be the ``data:`` field of an SSE event."""
        return self.model_dump_json()

    @property
    def is_terminal(self) -> bool:
        return self.event_type in {
            AgentEventType.ORCHESTRATION_COMPLETED,
            AgentEventType.ORCHESTRATION_FAILED,
        }
