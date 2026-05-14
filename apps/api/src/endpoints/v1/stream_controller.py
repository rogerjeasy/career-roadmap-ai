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

Wire format (each message):
    event: agent_event
    data: {"event_id":"...","event_type":"...","payload":{...}}

    (blank line terminates each SSE message)

Keepalive comments (`: keepalive`) are emitted every 15 s to prevent proxies
and load-balancers from closing idle connections during long agent phases.
"""
import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from agents.bus.channel import channel_for_session
from agents.bus.subscriber import subscribe_to_session
from agents.contracts.events import AgentEvent
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.db.redis import get_redis

router = APIRouter(prefix="/stream", tags=["streaming"])
logger = get_logger(__name__)

_STREAM_TIMEOUT_SECONDS = 300.0    # 5 min max per generation run
_HEARTBEAT_INTERVAL_SECONDS = 15.0  # SSE comment keepalive interval
_BRIDGE_QUEUE_SIZE = 256            # event buffer per connection
_BACKPRESSURE_WARN_DEPTH = 200      # log warning when buffer is >78% full
_BRIDGE_PUT_TIMEOUT_SECONDS = 5.0   # max wait to enqueue one event before drop


@router.get(
    "/{session_id}",
    summary="Subscribe to live agent events (SSE)",
    # Use base Response as response_class — FastAPI 0.136.x has a bug where
    # StreamingResponse subclasses crash the OpenAPI generator at schema
    # build time. response_class only affects docs, not what we return.
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
    The stream closes when ``ORCHESTRATION_COMPLETED`` or
    ``ORCHESTRATION_FAILED`` is received, or after the server-side timeout.

    Heartbeat SSE comments are emitted every ``_HEARTBEAT_INTERVAL_SECONDS``
    to prevent proxies from closing idle connections.
    """
    channel = channel_for_session(user.uid, session_id)
    logger.info("stream.subscribed", channel=channel, user_id=user.uid)

    async def _event_generator() -> AsyncGenerator[str, None]:
        # Immediate keepalive so the client knows the connection is open
        # before the first real event arrives.
        yield ": keepalive\n\n"

        # Bridge the subscriber into a bounded queue so we can interleave
        # heartbeat comments without cancelling the underlying async generator.
        # maxsize enforces backpressure: a slow consumer stalls the subscriber
        # rather than allowing unbounded memory growth.
        bridge: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize=_BRIDGE_QUEUE_SIZE)

        async def _drain_subscriber() -> None:
            try:
                async for event in subscribe_to_session(
                    redis_client,
                    channel,
                    timeout_seconds=_STREAM_TIMEOUT_SECONDS,
                ):
                    depth = bridge.qsize()
                    if depth >= _BACKPRESSURE_WARN_DEPTH:
                        logger.warning(
                            "stream.slow_consumer",
                            channel=channel,
                            queue_depth=depth,
                            queue_max=_BRIDGE_QUEUE_SIZE,
                        )
                    try:
                        await asyncio.wait_for(
                            bridge.put(event),
                            timeout=_BRIDGE_PUT_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        if event.is_terminal:
                            # Terminal events must be delivered — block until space opens.
                            await bridge.put(event)
                        else:
                            logger.error(
                                "stream.event_dropped",
                                channel=channel,
                                event_type=event.event_type,
                            )
                        continue
                    if event.is_terminal:
                        break
            except Exception as exc:
                logger.error(
                    "stream.subscriber_error", channel=channel, error=str(exc)
                )
            finally:
                # None sentinel signals exhaustion to the generator below.
                await bridge.put(None)

        drain_task = asyncio.create_task(_drain_subscriber())

        try:
            while True:
                if await request.is_disconnected():
                    logger.info("stream.client_disconnected", channel=channel)
                    return

                try:
                    item: AgentEvent | None = await asyncio.wait_for(
                        bridge.get(), timeout=_HEARTBEAT_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    # No event in the last interval — emit a keepalive comment.
                    yield ": keepalive\n\n"
                    continue

                if item is None:
                    # Subscriber exhausted — terminal event was already yielded.
                    return

                yield _format_sse(item)

                if item.is_terminal:
                    return

        except Exception as exc:
            logger.error("stream.error", channel=channel, error=str(exc))
            yield f"event: error\ndata: {json.dumps({'error': 'Stream interrupted', 'detail': str(exc)})}\n\n"
        finally:
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task

    return StreamingResponse(
        content=_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _format_sse(event: AgentEvent) -> str:
    """Format an AgentEvent as a single SSE message."""
    return f"event: agent_event\ndata: {event.to_sse_data()}\n\n"
