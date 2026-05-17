"""Intake controller — SSE-driven profile clarification before roadmap generation.

POST /api/v1/intake/start
    Reads the session profile, scores completeness, generates clarification
    questions for missing slots, and emits a CLARIFICATION_REQUIRED event to
    the user's SSE channel. Also returns career path suggestions (stored during
    CV upload) so the frontend can display them as chips.

POST /api/v1/intake/reply
    Receives the user's free-text reply to pending questions, parses structured
    values from it (via LLM), updates the session profile, re-scores, and emits
    either another CLARIFICATION_REQUIRED or CLARIFICATION_RESOLVED.
"""
from __future__ import annotations

import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from agents.bus.channel import channel_for_session
from agents.config import agent_settings
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import UserProfileSnapshot
from agents.orchestrator.clarification_engine import (
    ClarificationEngine,
    ClarificationQuestion as EngineClarificationQuestion,
)
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.db.redis import get_redis
from src.session.manager import SessionManager, get_session_manager
from src.session.models import ClarificationFlags, ClarificationQuestion, UserProfileContext

router = APIRouter(prefix="/intake", tags=["intake"])
logger = get_logger(__name__)

_REPLAY_TTL_SECONDS = 600
_engine = ClarificationEngine()


# ── Schemas ───────────────────────────────────────────────────────────────────


class IntakeStartResponse(BaseModel):
    session_id: str
    stream_channel: str


class IntakeReplyRequest(BaseModel):
    user_reply: str = Field(min_length=1, max_length=2000)


class IntakeReplyResponse(BaseModel):
    resolved: bool
    completeness: float


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _emit_event(redis_client: aioredis.Redis, event: AgentEvent) -> None:
    """Async Redis event publisher for use in API request handlers."""
    channel = channel_for_session(event.user_id, event.session_id)
    payload = event.model_dump_json()
    list_key = f"event_log:{channel}"
    pipe = redis_client.pipeline()
    pipe.rpush(list_key, payload)
    pipe.expire(list_key, _REPLAY_TTL_SECONDS)
    pipe.publish(channel, payload)
    await pipe.execute()
    logger.debug(
        "intake.event_emitted",
        event_type=event.event_type.value,
        channel=channel,
    )


def _to_profile_snapshot(ctx: UserProfileContext | None) -> UserProfileSnapshot:
    if ctx is None:
        return UserProfileSnapshot()
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
        additional=dict(ctx.additional),
    )


def _to_session_question(q: EngineClarificationQuestion) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=q.id,
        question=q.question,
        field_name=q.field_name,
        priority=q.priority,
    )


def _from_session_question(q: ClarificationQuestion) -> EngineClarificationQuestion:
    return EngineClarificationQuestion(
        question=q.question,
        field_name=q.field_name,
        priority=q.priority,
        id=q.id,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/start",
    response_model=IntakeStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start intake — scores profile and emits CLARIFICATION_REQUIRED via SSE",
)
async def intake_start(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> IntakeStartResponse:
    """Score the user's profile completeness and emit the first clarification event.

    The client must be subscribed to ``GET /stream/{session_id}`` before calling
    this endpoint so it receives the emitted event in real time.
    """
    session = await mgr.get_or_create(user.uid, user.email)
    session_id = user.uid
    stream_channel = channel_for_session(user.uid, session_id)
    correlation_id = str(uuid.uuid4())

    profile_ctx = session.user_profile_context or UserProfileContext()
    profile = _to_profile_snapshot(profile_ctx)
    score, missing_slots = _engine.score(profile, correlation_id=correlation_id)

    career_path_suggestions: list[str] = profile_ctx.additional.get(
        "career_path_suggestions", []
    )

    # Clear the event log from any previous intake run.
    list_key = f"event_log:{stream_channel}"
    await redis_client.delete(list_key)

    if missing_slots and score < agent_settings.completeness_threshold:
        questions = await _engine.generate_questions(
            profile,
            missing_slots,
            user_message="",
            n=1,
            correlation_id=correlation_id,
        )
        await mgr.set_follow_up_queue(
            user.uid,
            [_to_session_question(q) for q in questions],
            user.email,
        )
        event = AgentEvent(
            event_type=AgentEventType.CLARIFICATION_REQUIRED,
            session_id=session_id,
            user_id=user.uid,
            correlation_id=correlation_id,
            payload={
                "questions": [q.to_dict() for q in questions],
                "round": 1,
                "career_path_suggestions": career_path_suggestions,
                "completeness": score,
            },
        )
    else:
        event = AgentEvent(
            event_type=AgentEventType.CLARIFICATION_RESOLVED,
            session_id=session_id,
            user_id=user.uid,
            correlation_id=correlation_id,
            payload={
                "completeness": score,
                "career_path_suggestions": career_path_suggestions,
            },
        )

    await _emit_event(redis_client, event)
    logger.info(
        "intake.start",
        user_id=user.uid,
        score=score,
        missing=missing_slots,
        suggestions_count=len(career_path_suggestions),
    )

    return IntakeStartResponse(session_id=session_id, stream_channel=stream_channel)


@router.post(
    "/reply",
    response_model=IntakeReplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a reply to pending clarification questions",
)
async def intake_reply(
    body: IntakeReplyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> IntakeReplyResponse:
    """Parse the user's reply, update the session profile, and emit the next event.

    Emits ``CLARIFICATION_REQUIRED`` if more fields are missing and the round
    cap has not been reached; emits ``CLARIFICATION_RESOLVED`` otherwise.
    """
    session = await mgr.get_or_create(user.uid, user.email)
    session_id = user.uid
    stream_channel = channel_for_session(user.uid, session_id)
    correlation_id = str(uuid.uuid4())

    pending_questions = [_from_session_question(q) for q in session.follow_up_queue]

    parsed = await _engine.parse_answers(
        pending_questions,
        body.user_reply,
        correlation_id=correlation_id,
    )

    updated_session = await mgr.apply_clarification_answers(user.uid, parsed, user.email)
    updated_profile = _to_profile_snapshot(updated_session.user_profile_context)

    new_score, remaining_slots = _engine.score(updated_profile, correlation_id=correlation_id)
    round_number = updated_session.clarification_flags.round_number
    resolved = (
        new_score >= agent_settings.completeness_threshold
        or round_number >= agent_settings.max_clarification_rounds
        or not remaining_slots
    )

    if resolved:
        await mgr.update_clarification_flags(
            user.uid,
            ClarificationFlags(
                completeness_score=new_score,
                missing_slots=remaining_slots,
                round_number=round_number,
                is_complete=True,
            ),
            user.email,
        )
        event = AgentEvent(
            event_type=AgentEventType.CLARIFICATION_RESOLVED,
            session_id=session_id,
            user_id=user.uid,
            correlation_id=correlation_id,
            payload={
                "completeness": new_score,
                "applied_fields": list(parsed.keys()),
            },
        )
    else:
        questions = await _engine.generate_questions(
            updated_profile,
            remaining_slots,
            user_message="",
            n=1,
            correlation_id=correlation_id,
        )
        await mgr.set_follow_up_queue(
            user.uid,
            [_to_session_question(q) for q in questions],
            user.email,
        )
        event = AgentEvent(
            event_type=AgentEventType.CLARIFICATION_REQUIRED,
            session_id=session_id,
            user_id=user.uid,
            correlation_id=correlation_id,
            payload={
                "questions": [q.to_dict() for q in questions],
                "round": round_number + 1,
                "completeness": new_score,
            },
        )

    await _emit_event(redis_client, event)
    logger.info(
        "intake.reply",
        user_id=user.uid,
        parsed_fields=list(parsed.keys()),
        new_score=new_score,
        resolved=resolved,
    )

    return IntakeReplyResponse(resolved=resolved, completeness=new_score)
