"""Session & Context Manager — HTTP endpoints.

All routes require a valid Firebase ID token. The session is keyed by the
Firebase UID so each user has exactly one active session at a time.
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import NotFoundError
from src.session.manager import SessionManager, get_session_manager
from src.session.models import ClarificationFlags, PlanContext, UserProfileContext
from src.session.schemas import (
    AddConversationTurnRequest,
    ClarificationReplyRequest,
    SessionStateResponse,
    SetFollowUpQueueRequest,
    SetPlanContextRequest,
    UpdateClarificationFlagsRequest,
    UpdateUserProfileContextRequest,
)

router = APIRouter(prefix="/session", tags=["session"])


async def _require_session(
    user: AuthenticatedUser,
    mgr: SessionManager,
) -> SessionStateResponse:
    """Load session or raise 404 — used by endpoints that must not auto-create."""
    session = await mgr.get(user.uid)
    if session is None:
        raise NotFoundError("No active session — start a roadmap generation request first")
    return SessionStateResponse.from_session(session)


# ── Session lifecycle ─────────────────────────────────────────────────────────


@router.get("", response_model=SessionStateResponse)
async def get_session(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Return the current session state, creating a new one if none exists."""
    session = await mgr.get_or_create(user.uid, user.email)
    return SessionStateResponse.from_session(session)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> None:
    """Delete the session. A fresh one is created on the next request."""
    await mgr.delete(user.uid)


# ── Clarification queue ───────────────────────────────────────────────────────


@router.get("/clarification", response_model=list)
async def get_clarification_questions(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> list:
    """Return pending clarification questions from the follow-up queue."""
    session = await mgr.get(user.uid)
    if session is None:
        return []
    return [q.model_dump() for q in session.follow_up_queue]


@router.post("/clarification/reply", response_model=SessionStateResponse)
async def reply_clarification(
    body: ClarificationReplyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Merge user answers into the profile context and clear the follow-up queue."""
    session = await mgr.apply_clarification_answers(user.uid, body.answers, user.email)
    return SessionStateResponse.from_session(session)


@router.post("/clarification/queue", response_model=SessionStateResponse)
async def set_clarification_queue(
    body: SetFollowUpQueueRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Push a new set of clarification questions (called by the Clarification Engine)."""
    session = await mgr.set_follow_up_queue(user.uid, body.questions, user.email)
    return SessionStateResponse.from_session(session)


@router.patch("/clarification/flags", response_model=SessionStateResponse)
async def update_clarification_flags(
    body: UpdateClarificationFlagsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Update clarification scoring metadata (completeness score, missing slots, etc.)."""
    session = await mgr.get_or_create(user.uid, user.email)
    flags = session.clarification_flags
    if body.completeness_score is not None:
        flags.completeness_score = body.completeness_score
    if body.missing_slots is not None:
        flags.missing_slots = body.missing_slots
    if body.round_number is not None:
        flags.round_number = body.round_number
    if body.is_complete is not None:
        flags.is_complete = body.is_complete
    updated = await mgr.update_clarification_flags(user.uid, flags, user.email)
    return SessionStateResponse.from_session(updated)


# ── Conversation state ────────────────────────────────────────────────────────


@router.post("/conversation", response_model=SessionStateResponse, status_code=status.HTTP_201_CREATED)
async def add_conversation_turn(
    body: AddConversationTurnRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Append a conversation turn to the dialogue history."""
    session = await mgr.add_turn(user.uid, body.role, body.content, user.email)
    return SessionStateResponse.from_session(session)


# ── Context caches ────────────────────────────────────────────────────────────


@router.patch("/user-profile", response_model=SessionStateResponse)
async def update_user_profile_context(
    body: UpdateUserProfileContextRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Replace or merge fields into the cached user profile context."""
    session = await mgr.get_or_create(user.uid, user.email)
    existing = session.user_profile_context or UserProfileContext()

    # Only overwrite fields that were explicitly provided in the request
    update_data = body.model_dump(exclude_none=True)
    merged = existing.model_copy(update=update_data)

    updated = await mgr.set_user_profile_context(user.uid, merged, user.email)
    return SessionStateResponse.from_session(updated)


@router.patch("/plan", response_model=SessionStateResponse)
async def update_plan_context(
    body: SetPlanContextRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Update the cached roadmap/plan context snapshot."""
    session = await mgr.get_or_create(user.uid, user.email)
    existing = session.plan_context or PlanContext()

    update_data = body.model_dump(exclude_none=True)
    merged = existing.model_copy(update=update_data)

    updated = await mgr.set_plan_context(user.uid, merged, user.email)
    return SessionStateResponse.from_session(updated)
