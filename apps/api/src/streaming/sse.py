"""Server-Sent Events (SSE) helpers for streaming agent output to clients."""
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse


async def event_stream(
    generator: AsyncGenerator[str, None],
    event_type: str = "message",
) -> AsyncGenerator[str, None]:
    """Wraps an async string generator as SSE-formatted events."""
    async for data in generator:
        yield f"event: {event_type}\ndata: {data}\n\n"
    yield "event: done\ndata: [DONE]\n\n"


class SSEResponse(StreamingResponse):
    """StreamingResponse pre-configured for SSE with no-cache headers."""

    media_type = "text/event-stream"

    def __init__(
        self,
        generator: AsyncGenerator[str, None],
        event_type: str = "message",
        **kwargs,
    ) -> None:
        super().__init__(
            content=event_stream(generator, event_type),
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            **kwargs,
        )
