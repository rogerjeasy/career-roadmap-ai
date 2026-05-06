"""Session & Context Manager — API request/response schemas.

snake_case fields; CaseConversionMiddleware handles camelCase↔snake_case at
the HTTP boundary so frontend receives camelCase automatically.
"""
from typing import Any

from src.core.schema import BaseSchema
from src.session.models import (
    ClarificationFlags,
    ClarificationQuestion,
    ConversationRole,
    ConversationTurn,
    PlanContext,
    SessionData,
    UserProfileContext,
)


class SessionStateResponse(BaseSchema):
    """Full session state returned to the client."""
    user_id: str
    email: str | None
    created_at: str  # ISO-8601 string for JSON transport
    last_active_at: str
    conversation_state: list[ConversationTurn]
    follow_up_queue: list[ClarificationQuestion]
    clarification_flags: ClarificationFlags
    user_profile_context: UserProfileContext | None
    plan_context: PlanContext | None

    @classmethod
    def from_session(cls, session: SessionData) -> "SessionStateResponse":
        return cls(
            user_id=session.user_id,
            email=session.email,
            created_at=session.created_at.isoformat(),
            last_active_at=session.last_active_at.isoformat(),
            conversation_state=session.conversation_state,
            follow_up_queue=session.follow_up_queue,
            clarification_flags=session.clarification_flags,
            user_profile_context=session.user_profile_context,
            plan_context=session.plan_context,
        )


class ClarificationReplyRequest(BaseSchema):
    """Answers submitted by the user in response to clarification questions.

    Keys are `field_name` values from the ClarificationQuestion items; values
    are the user-supplied answers (string scalars or lists).
    """
    answers: dict[str, Any]


class AddConversationTurnRequest(BaseSchema):
    role: ConversationRole
    content: str


class SetFollowUpQueueRequest(BaseSchema):
    """Used internally by the Clarification Engine to push questions."""
    questions: list[ClarificationQuestion]


class UpdateUserProfileContextRequest(BaseSchema):
    target_role: str | None = None
    current_role: str | None = None
    skills: list[str] | None = None
    goals: list[str] | None = None
    constraints: list[str] | None = None
    location: str | None = None
    timeline_months: int | None = None
    weekly_hours_available: int | None = None
    salary_goal: int | None = None
    additional: dict[str, Any] | None = None


class SetPlanContextRequest(BaseSchema):
    roadmap_id: str | None = None
    snapshot: dict[str, Any] | None = None


class UpdateClarificationFlagsRequest(BaseSchema):
    completeness_score: float | None = None
    missing_slots: list[str] | None = None
    round_number: int | None = None
    is_complete: bool | None = None
