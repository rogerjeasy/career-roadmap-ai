"""Real-time agent event stream — Server-Sent Events endpoint.

GET /api/v1/stream/{session_id}
    Subscribes to the Redis pub/sub channel for the given session and
    forwards each ``AgentEvent`` to the client as an SSE event.
    Terminates when the orchestration completes, fails, or the timeout elapses.

The client drives the full interaction loop:
  1. POST /orchestrator/generate → receive request_id + stream_channel
  2. Subscribe GET /stream/{session_id} → receive live events
  3. When CLARIFICATION_REQUIRED event arrives → POST /session/clarification/reply
  4. POST /orchestrator/generate again with enriched profile
  5. ORCHESTRATION_COMPLETED event carries the final roadmap payload
"""
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from agents.bus.channel import channel_for_session
from agents.bus.subscriber import subscribe_to_session
from agents.contracts.events import AgentEvent
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.db.redis import get_redis
from src.streaming.sse import SSEResponse

router = APIRouter(prefix="/stream", tags=["streaming"])
logger = get_logger(__name__)

_STREAM_TIMEOUT_SECONDS = 300.0  # 5 minutes max per generation request


@router.get(
    "/{session_id}",
    summary="Subscribe to live agent events (SSE)",
    # Use base Response (not SSEResponse) as response_class — FastAPI 0.136.x has a
    # bug where StreamingResponse subclasses crash the OpenAPI generator at schema
    # build time. response_class only affects OpenAPI docs, not what we actually return.
    response_class=Response,
    response_model=None,
    responses={
        200: {
            "description": (
                "Server-Sent Events stream. Each event is a JSON-encoded AgentEvent "
                "emitted as `event: agent_event\\ndata: {...}\\n\\n`. "
                "The stream closes on ORCHESTRATION_COMPLETED or ORCHESTRATION_FAILED."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: agent_event\ndata: {"event_type":"agent_started"}\n\n',
                }
            },
        }
    },
)
async def stream_agent_events(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """Subscribe to the Redis pub/sub channel and forward events as SSE.

    Each event is a JSON-encoded ``AgentEvent`` in the ``data:`` field.
    The stream closes when an ``ORCHESTRATION_COMPLETED`` or
    ``ORCHESTRATION_FAILED`` event is received.

    Client-side usage::

        const es = new EventSource('/api/v1/stream/<session_id>', {
            headers: { Authorization: 'Bearer <token>' }
        });
        es.addEventListener('agent_event', (e) => {
            const event = JSON.parse(e.data);
            // handle event.event_type ...
        });
    """
    channel = channel_for_session(user.uid, session_id)
    logger.info("stream.subscribed", channel=channel, user_id=user.uid)

    async def _event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in subscribe_to_session(
                redis_client,
                channel,
                timeout_seconds=_STREAM_TIMEOUT_SECONDS,
            ):
                # Check for client disconnect to avoid unnecessary Redis reads
                if await request.is_disconnected():
                    logger.info("stream.client_disconnected", channel=channel)
                    break
                yield _format_sse(event)
        except Exception as exc:
            logger.error("stream.error", channel=channel, error=str(exc))
            # Emit an error event so the client can surface it gracefully
            yield (
                'event: error\n'
                f'data: {{"error": "Stream interrupted", "detail": "{exc}"}}\n\n'
            )

    return SSEResponse(generator=_event_generator(), event_type="agent_event")


def _format_sse(event: AgentEvent) -> str:
    """Format an AgentEvent as an SSE message string."""
    return f"event: agent_event\ndata: {event.to_sse_data()}\n\n"
