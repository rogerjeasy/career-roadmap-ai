"""Orchestrator — HTTP endpoints for roadmap generation.

POST /api/v1/orchestrator/generate
    Validates the request, builds an ``OrchestratorTaskInput``, dispatches it
    to the Celery queue via ``TaskPublisher``, and returns the ``request_id``
    immediately (fire-and-forget).  The client then subscribes to the SSE
    stream (``/api/v1/stream/{session_id}``) to receive live progress events
    and the final roadmap.

GET /api/v1/orchestrator/status/{request_id}
    Returns the Celery task status and result when the task has completed.
    Useful as a polling fallback if the client does not support SSE.
"""
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from pydantic import BaseModel, Field

from agents.bus.channel import channel_for_session
from agents.bus.publisher import TaskPublisher
from agents.contracts.tasks import OrchestratorTaskInput, UserProfileSnapshot
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger
from src.db.redis import get_redis
from src.session.manager import SessionManager, get_session_manager
from src.session.models import UserProfileContext

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

_task_publisher = TaskPublisher()


# ── Request / response schemas ────────────────────────────────────────────────


class GenerateRoadmapRequest(BaseModel):
    """Body for POST /orchestrator/generate."""

    message: str = Field(
        description="The user's career goal or natural-language request.",
        min_length=10,
        max_length=2000,
    )


class GenerateRoadmapResponse(BaseModel):
    request_id: str
    session_id: str
    stream_channel: str
    message: str = "Roadmap generation started. Subscribe to the stream for live updates."


class TaskStatusResponse(BaseModel):
    request_id: str
    state: str
    result: dict | None = None
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_profile_snapshot(ctx: UserProfileContext | None) -> UserProfileSnapshot:
    """Convert the session's profile context to the agents-package snapshot type.

    This is the ONLY place where an apps/api type is converted to an
    agents.contracts type.  All other code on both sides uses their own types.
    """
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


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/generate",
    response_model=GenerateRoadmapResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start asynchronous roadmap generation",
)
async def generate_roadmap(
    body: GenerateRoadmapRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> GenerateRoadmapResponse:
    """Dispatch a roadmap generation request to the agent pipeline.

    Returns immediately with ``request_id`` and ``stream_channel``.
    The client should subscribe to ``GET /stream/{session_id}`` to receive
    live agent progress events and the final synthesised roadmap.
    """
    session = await mgr.get_or_create(user.uid, user.email)
    stream_channel = channel_for_session(user.uid, session.user_id)

    with tracer.start_as_current_span("orchestrator.generate") as span:
        span.set_attribute("user.id", user.uid)
        span.set_attribute("session.id", session.user_id)
        span.set_attribute("stream.channel", stream_channel)

        # Purge the event replay log from any previous run so a subscriber that
        # connects after this 202 response never replays stale terminal events.
        replay_log_key = f"event_log:{stream_channel}"
        await redis_client.delete(replay_log_key)

        task_input = OrchestratorTaskInput(
            session_id=session.user_id,
            user_id=user.uid,
            user_message=body.message,
            user_profile=_to_profile_snapshot(session.user_profile_context),
            stream_channel=stream_channel,
        )

        try:
            task_id = _task_publisher.dispatch_orchestration(task_input)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            logger.error(
                "orchestrator.dispatch_failed",
                error=str(exc),
                user_id=user.uid,
            )
            raise ExternalServiceError(
                "Failed to start roadmap generation. Please try again."
            ) from exc

        span.set_attribute("task.id", task_id)
        logger.info(
            "orchestrator.generation_dispatched",
            task_id=task_id,
            user_id=user.uid,
            session_id=session.user_id,
        )

    return GenerateRoadmapResponse(
        request_id=task_id,
        session_id=session.user_id,
        stream_channel=stream_channel,
    )


@router.get(
    "/status/{request_id}",
    response_model=TaskStatusResponse,
    summary="Poll task status (SSE fallback)",
)
async def get_task_status(
    request_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> TaskStatusResponse:
    """Return the current state of a Celery task by ID.

    Prefer the SSE stream for real-time updates; use this endpoint as a
    polling fallback for clients that do not support SSE.
    """
    from agents.bus.celery_app import celery_app  # noqa: PLC0415
    from celery.result import AsyncResult  # noqa: PLC0415

    with tracer.start_as_current_span("orchestrator.task_status") as span:
        span.set_attribute("user.id", user.uid)
        span.set_attribute("task.id", request_id)

        result: AsyncResult = celery_app.AsyncResult(request_id)
        state = result.state
        span.set_attribute("task.state", state)

        if state == "SUCCESS":
            return TaskStatusResponse(request_id=request_id, state=state, result=result.result)
        if state == "FAILURE":
            return TaskStatusResponse(
                request_id=request_id, state=state, error=str(result.result)
            )
        return TaskStatusResponse(request_id=request_id, state=state)
