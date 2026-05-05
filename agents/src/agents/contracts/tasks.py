"""Agent task input types — serialisable payloads sent across the bus.

These are pure-Pydantic, zero-framework types. They are serialised to JSON
when crossing the Celery/Redis boundary and deserialised on the worker side.
The API constructs these from its own domain models; agents consume them.
Neither side imports from the other.
"""
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Identifies every specialist agent in the system."""

    INTAKE = "intake"
    CV_ANALYSIS = "cv_analysis"
    GAP_ANALYSIS = "gap_analysis"
    MARKET_INTELLIGENCE = "market_intelligence"
    ROADMAP_GENERATION = "roadmap_generation"
    VALIDATOR = "validator"
    LEARNING_RESOURCES = "learning_resources"
    NETWORKING = "networking"
    OPPORTUNITY = "opportunity"
    PROGRESS = "progress"
    COACH = "coach"


class TaskPriority(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10


class UserProfileSnapshot(BaseModel):
    """Serialisable snapshot of the user profile passed to every agent.

    Mirrors ``apps/api/src/session/models.UserProfileContext`` in shape but
    is independently defined so the agents package has no import of the API.
    Kept in sync via the serialisation contract documented in contracts/.
    """

    target_role: str | None = None
    current_role: str | None = None
    skills: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    location: str | None = None
    timeline_months: int | None = None
    weekly_hours_available: int | None = None
    salary_goal: int | None = None
    additional: dict[str, Any] = Field(default_factory=dict)


class AgentTaskInput(BaseModel):
    """Envelope for a single specialist-agent invocation.

    Created by ``TaskDispatcher``; serialised by Celery; consumed by the
    concrete agent via ``BaseAgent.run()``.
    """

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_type: AgentType
    session_id: str
    user_id: str
    priority: TaskPriority = TaskPriority.NORMAL
    user_profile: UserProfileSnapshot
    payload: dict[str, Any] = Field(default_factory=dict)
    # Ties all sub-tasks for one generation request together
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))


class OrchestratorTaskInput(BaseModel):
    """Top-level orchestration request sent by the API to the Orchestrator.

    The API POSTs to ``/api/v1/orchestrator/generate``, the controller
    builds this object and hands it to ``TaskPublisher.dispatch_orchestration``.

    Multi-turn clarification fields:
    - ``clarification_round`` — 0 for the first invocation; the API increments
      this on each re-invocation after a ``CLARIFICATION_REQUIRED`` event.
    - ``previous_clarification_questions`` — the questions surfaced in the
      previous round, serialised as plain dicts so the answer-parser can map
      the user's reply back to specific fields.  Empty on round 0.
    """

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    user_id: str
    user_message: str
    user_profile: UserProfileSnapshot
    # Redis pub/sub channel the API subscribes on for event streaming
    stream_channel: str
    # Multi-turn clarification tracking
    clarification_round: int = Field(default=0, ge=0)
    previous_clarification_questions: list[dict[str, Any]] = Field(
        default_factory=list
    )
    # When set, the intent parser skips LLM detection and uses this value directly.
    # Used by the coach endpoint to force ``coach_query`` without an extra LLM hop.
    forced_intent: str | None = None
