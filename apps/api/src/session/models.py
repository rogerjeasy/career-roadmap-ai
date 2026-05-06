"""Session & Context Manager — internal Pydantic data models.

All session state lives in Redis under `session:{user_id}` as a single JSON
document. Sub-models are composed into SessionData for atomic reads/writes.
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ConversationRole(str, Enum):
    user = "user"
    assistant = "assistant"


class ConversationTurn(BaseModel):
    role: ConversationRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClarificationQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    field_name: str  # e.g. "weekly_hours", "salary_goal", "location"
    priority: int = 1  # 1 = highest blocking impact


class ClarificationFlags(BaseModel):
    completeness_score: float = 0.0  # 0.0–1.0; generation gates at configured threshold
    missing_slots: list[str] = []
    round_number: int = 0  # increments per clarification cycle; capped at 3
    is_complete: bool = False


class UserProfileContext(BaseModel):
    """Structured user profile cached during the session for all specialist agents."""
    target_role: str | None = None
    current_role: str | None = None
    skills: list[str] = []
    goals: list[str] = []
    constraints: list[str] = []
    location: str | None = None
    timeline_months: int | None = None
    weekly_hours_available: int | None = None
    salary_goal: int | None = None  # annual, in user's local currency
    additional: dict[str, Any] = Field(default_factory=dict)


class PlanContext(BaseModel):
    """Lightweight roadmap snapshot cached while agents are processing."""
    roadmap_id: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime | None = None


# Maximum number of conversation turns kept in Redis to bound payload size.
MAX_CONVERSATION_TURNS = 100


class SessionData(BaseModel):
    user_id: str
    email: str | None
    created_at: datetime
    last_active_at: datetime
    conversation_state: list[ConversationTurn] = []
    follow_up_queue: list[ClarificationQuestion] = []
    clarification_flags: ClarificationFlags = Field(default_factory=ClarificationFlags)
    user_profile_context: UserProfileContext | None = None
    plan_context: PlanContext | None = None
