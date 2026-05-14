"""Agent result types — structured outputs returned after each agent run."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentResultStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class AgentResult(BaseModel):
    """Structured output from a single specialist agent run."""

    task_id: str
    agent_type: str
    status: AgentResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    error_message: str | None = None
    duration_ms: int = 0


class OrchestratorResult(BaseModel):
    """Final synthesised output returned by the Master Orchestrator.

    Persisted to Celery result backend; also emitted as the payload of the
    ``ORCHESTRATION_COMPLETED`` event on the Redis pub/sub channel.
    """

    request_id: str
    session_id: str
    user_id: str
    status: AgentResultStatus
    roadmap: dict[str, Any] | None = None
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_passed: bool = True
    clarification_required: bool = False
    clarification_questions: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    duration_ms: int = 0
