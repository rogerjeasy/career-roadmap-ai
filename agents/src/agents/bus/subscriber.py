"""Async Redis pub/sub subscriber — used by the API's SSE/WebSocket layer.

``subscribe_to_session`` is an async generator that yields ``AgentEvent``
objects from a per-session channel until the orchestration completes or
the timeout elapses.  The FastAPI controller drives this generator and
forwards events as Server-Sent Events.
"""
import asyncio
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
import structlog

from agents.contracts.events import AgentEvent
from agents.core.exceptions import BusSubscribeError

logger = structlog.get_logger(__name__)

# Buffer size for the asyncio queue that bridges the pub/sub reader task
# and the generator consumer.
_QUEUE_SIZE = 256


async def subscribe_to_session(
    redis_client: aioredis.Redis,
    channel: str,
    timeout_seconds: float = 300.0,
) -> AsyncGenerator[AgentEvent, None]:
    """Yield ``AgentEvent`` objects from a Redis pub/sub channel.

    Terminates when:
    - An ``ORCHESTRATION_COMPLETED`` or ``ORCHESTRATION_FAILED`` event arrives.
    - ``timeout_seconds`` elapses without a terminal event.

    Usage::

        async for event in subscribe_to_session(redis, channel):
            yield f"data: {event.to_sse_data()}\\n\\n"
    """
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize=_QUEUE_SIZE)
    pubsub = redis_client.pubsub()

    async def _reader() -> None:
        """Background task: reads from pub/sub and enqueues parsed events."""
        try:
            await pubsub.subscribe(channel)
            logger.info("bus.subscriber.connected", channel=channel)
            deadline = asyncio.get_event_loop().time() + timeout_seconds

            while asyncio.get_event_loop().time() < deadline:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    continue
                try:
                    event = AgentEvent.model_validate_json(message["data"])
                    await queue.put(event)
                    if event.is_terminal:
                        break
                except Exception as exc:
                    logger.warning("bus.subscriber.parse_error", error=str(exc))

        except Exception as exc:
            raise BusSubscribeError(f"Pub/sub subscription failed: {exc}") from exc
        finally:
            await queue.put(None)  # sentinel — signals generator to stop
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.info("bus.subscriber.disconnected", channel=channel)

    reader_task = asyncio.create_task(_reader())

    try:
        while True:
            item = await asyncio.wait_for(queue.get(), timeout=timeout_seconds + 5)
            if item is None:
                break
            yield item
            if item.is_terminal:
                break
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
