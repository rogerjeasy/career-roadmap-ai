"""Application middleware — rate limiting, case conversion, and trace context."""
import json
from urllib.parse import parse_qsl, urlencode

import structlog
from fastapi import FastAPI
from opentelemetry import trace as otel_trace
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.config import settings
from src.core.case_converter import keys_to_camel, keys_to_snake, to_snake_case

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=str(settings.redis_url),
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)


def setup_rate_limiter(app: FastAPI) -> None:
    """Mount limiter state and 429 handler onto the app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Trace context middleware ──────────────────────────────────────────────────


class TraceContextMiddleware:
    """Bind the active OTel trace_id/span_id into structlog context vars.

    Runs inside the OTel ASGI wrapper so the span is already active. Clears
    context vars first to prevent leakage between concurrent async requests.
    When tracing is disabled the span context is invalid and nothing is bound.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            structlog.contextvars.clear_contextvars()
            ctx = otel_trace.get_current_span().get_span_context()
            if ctx.is_valid:
                structlog.contextvars.bind_contextvars(
                    trace_id=format(ctx.trace_id, "032x"),
                    span_id=format(ctx.span_id, "016x"),
                )
        await self.app(scope, receive, send)


# ── Case conversion middleware ────────────────────────────────────────────────

class CaseConversionMiddleware:
    """
    Pure-ASGI middleware that enforces the camelCase ↔ snake_case boundary.

    Pipeline:
        request  (camelCase)  → keys_to_snake  → FastAPI handlers (snake_case)
        response (snake_case) → keys_to_camel  → client          (camelCase)

    Handles:
      • JSON request bodies  (POST / PUT / PATCH)
      • Query-string keys
      • JSON response bodies (all status codes, including 4xx / 5xx)

    Skips non-JSON payloads (multipart, form-data, binary) transparently.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ── Query params: camelCase → snake_case ──────────────────────────────
        qs: bytes = scope.get("query_string", b"")
        if qs:
            pairs = parse_qsl(qs.decode(), keep_blank_values=True)
            scope = dict(scope)
            scope["query_string"] = urlencode(
                [(to_snake_case(k), v) for k, v in pairs]
            ).encode()

        # ── Request body + response body ──────────────────────────────────────
        await self.app(scope, _RequestReceiver(receive), _ResponseSender(send))


class _RequestReceiver:
    """Wraps the ASGI receive channel to convert JSON body keys to snake_case."""

    __slots__ = ("_receive", "_done")

    def __init__(self, receive: Receive) -> None:
        self._receive = receive
        self._done = False

    async def __call__(self) -> Message:
        if self._done:
            # Body already consumed — delegate all subsequent messages (e.g. disconnect)
            return await self._receive()

        # Collect all body chunks (handles chunked transfer transparently)
        chunks: list[bytes] = []
        while True:
            msg = await self._receive()
            if msg["type"] != "http.request":
                return msg  # unexpected message type — pass through
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body", False):
                break

        self._done = True
        body = b"".join(chunks)

        if body:
            try:
                body = json.dumps(keys_to_snake(json.loads(body))).encode()
            except (ValueError, TypeError):
                pass  # non-JSON body — pass through unchanged

        return {"type": "http.request", "body": body, "more_body": False}


class _ResponseSender:
    """Wraps the ASGI send channel to convert JSON response body keys to camelCase."""

    __slots__ = ("_send", "_start_msg", "_is_json", "_chunks")

    def __init__(self, send: Send) -> None:
        self._send = send
        self._start_msg: Message | None = None
        self._is_json: bool = False
        self._chunks: list[bytes] = []

    async def __call__(self, message: Message) -> None:
        mtype = message["type"]

        if mtype == "http.response.start":
            headers: list[tuple[bytes, bytes]] = message.get("headers", [])
            self._is_json = any(
                k.lower() == b"content-type" and b"application/json" in v.lower()
                for k, v in headers
            )
            if self._is_json:
                self._start_msg = message  # hold until we have the full body
            else:
                await self._send(message)

        elif mtype == "http.response.body":
            if not self._is_json:
                await self._send(message)
                return

            self._chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return  # wait for remaining chunks

            # Full body received — convert keys and flush
            body = b"".join(self._chunks)
            if body:
                try:
                    body = json.dumps(
                        keys_to_camel(json.loads(body)), default=str
                    ).encode()
                except (ValueError, TypeError):
                    pass  # malformed JSON — send as-is

            # Rebuild headers with the correct Content-Length
            orig_headers: list[tuple[bytes, bytes]] = self._start_msg.get("headers", [])
            new_headers = [
                (k, str(len(body)).encode()) if k.lower() == b"content-length" else (k, v)
                for k, v in orig_headers
            ]

            await self._send({**self._start_msg, "headers": new_headers})
            await self._send({"type": "http.response.body", "body": body, "more_body": False})

        else:
            await self._send(message)
