"""Coach — HTTP endpoint for the always-on conversational career coach.

POST /api/v1/coach/chat
    Dispatches a ``coach_query`` orchestration task with:
    - The user's message
    - Conversation history (from session) packed into the profile snapshot
    - Plan context (from session) packed into the profile snapshot
    Returns immediately with ``request_id`` and ``stream_channel``.
    The client subscribes to ``GET /stream/{session_id}`` for the SSE stream.

GET /api/v1/coach/history
    Returns the last N conversation turns for the authenticated user.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agents.bus.channel import channel_for_session
from agents.bus.publisher import TaskPublisher
from agents.contracts.tasks import OrchestratorTaskInput, UserProfileSnapshot
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger
from src.session.manager import SessionManager, get_session_manager
from src.session.models import ConversationRole, UserProfileContext

router = APIRouter(prefix="/coach", tags=["coach"])
logger = get_logger(__name__)

_task_publisher = TaskPublisher()


# ── Schemas ───────────────────────────────────────────────────────────────────


class CoachChatRequest(BaseModel):
    message: str = Field(
        description="The user's career question or coaching request.",
        min_length=2,
        max_length=2000,
    )


class CoachChatResponse(BaseModel):
    request_id: str
    session_id: str
    stream_channel: str
    message: str = "Coaching response starting. Subscribe to the stream for live output."


class ConversationTurnOut(BaseModel):
    role: str
    content: str
    timestamp: str


class HistoryResponse(BaseModel):
    turns: list[ConversationTurnOut]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/chat",
    response_model=CoachChatResponse,
    status_code=202,
    summary="Send a message to the career coach",
)
async def coach_chat(
    body: CoachChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> CoachChatResponse:
    """Dispatch a coaching query.

    Saves the user turn to conversation history, then dispatches a
    ``coach_query`` orchestration with conversation history and plan context
    injected into the profile snapshot's ``additional`` field.
    The client subscribes to the SSE stream for the coaching response.
    """
    # Load / create session and persist the user turn
    session = await mgr.get_or_create(user.uid, user.email)
    await mgr.add_turn(user.uid, ConversationRole.user, body.message, email=user.email)

    stream_channel = channel_for_session(user.uid, session.user_id)

    # Serialize conversation history for the agent context
    history = [
        {"role": t.role.value, "content": t.content}
        for t in session.conversation_state[-20:]  # last 20 turns
    ]

    # Serialize plan context (lightweight roadmap snapshot) for the agent
    plan_ctx: dict = {}
    if session.plan_context:
        plan_ctx = {
            "roadmap_id": session.plan_context.roadmap_id,
            "snapshot": session.plan_context.snapshot,
        }

    profile_snapshot = _to_profile_snapshot_with_context(
        ctx=session.user_profile_context,
        conversation_history=history,
        plan_context=plan_ctx,
    )

    task_input = OrchestratorTaskInput(
        session_id=session.user_id,
        user_id=user.uid,
        user_message=body.message,
        user_profile=profile_snapshot,
        stream_channel=stream_channel,
        forced_intent="coach_query",
    )

    try:
        task_id = _task_publisher.dispatch_orchestration(task_input)
    except Exception as exc:
        logger.error(
            "coach.dispatch_failed",
            error=str(exc),
            user_id=user.uid,
        )
        raise ExternalServiceError(
            "Failed to start coaching session. Please try again."
        ) from exc

    logger.info(
        "coach.chat_dispatched",
        task_id=task_id,
        user_id=user.uid,
        session_id=session.user_id,
        message_length=len(body.message),
    )

    return CoachChatResponse(
        request_id=task_id,
        session_id=session.user_id,
        stream_channel=stream_channel,
    )


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get conversation history with the coach",
)
async def get_coach_history(
    limit: int = 20,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> HistoryResponse:
    """Return the last ``limit`` conversation turns for the current user."""
    session = await mgr.get(user.uid)
    if not session:
        return HistoryResponse(turns=[], total=0)

    turns = session.conversation_state[-limit:]
    return HistoryResponse(
        turns=[
            ConversationTurnOut(
                role=t.role.value,
                content=t.content,
                timestamp=t.timestamp.isoformat(),
            )
            for t in turns
        ],
        total=len(session.conversation_state),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_profile_snapshot_with_context(
    ctx: UserProfileContext | None,
    conversation_history: list[dict],
    plan_context: dict,
) -> UserProfileSnapshot:
    """Build a UserProfileSnapshot with coaching context packed into ``additional``."""
    base: dict = {}
    if ctx:
        base = dict(ctx.additional)

    base["conversation_history"] = conversation_history
    base["plan_context"] = plan_context

    if ctx is None:
        return UserProfileSnapshot(additional=base)

    return UserProfileSnapshot(
        target_role=ctx.target_role,
        current_role=ctx.current_role,
        skills=list(ctx.skills),
        goals=list(ctx.goals),
        constraints=list(ctx.constraints),
        location=ctx.location,
        timeline_months=ctx.timeline_months,
        weekly_hours_available=ctx.weekly_hours_available,
        salary_goal=ctx.salary_goal,
        additional=base,
    )
