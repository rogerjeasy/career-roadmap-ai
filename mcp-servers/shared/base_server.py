"""Base FastAPI application factory for all MCP tool servers.

Every MCP server extends this base:

1. Mounts a ``POST /`` JSON-RPC 2.0 dispatcher with:
   - W3C traceparent extraction → OTel child spans propagate from agent calls
   - Correlation ID binding → structlog context vars for every log in the request
   - Per-request timeout (default 30 s) to prevent runaway upstream calls
2. Exposes ``GET /livez`` and ``GET /readyz`` health endpoints
3. Exposes ``GET /metrics`` for Prometheus scraping
4. Initialises structured logging, OpenTelemetry, and Sentry on startup

Each server registers its tool handlers via ``register_tool``::

    app = create_mcp_app(server_id="job_board", version="0.1.0")

    @app.register_tool("search_jobs")
    async def search_jobs(params: dict, request: Request) -> dict:
        ...

The dispatcher at ``POST /`` routes ``method`` → registered handler.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from shared.error_handler import (
    JsonRpcError,
    JsonRpcErrorCode,
    make_error_response,
    make_success_response,
)

_ToolHandler = Callable[..., Coroutine[Any, Any, dict[str, Any]]]

logger = structlog.get_logger(__name__)

# Default per-request timeout — overridden per-server via MCPApp(request_timeout=N)
_DEFAULT_REQUEST_TIMEOUT = float(os.getenv("MCP_REQUEST_TIMEOUT_S", "30"))


# ── Correlation-ID middleware ─────────────────────────────────────────────────

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Binds correlation_id, user_id, and server_id into structlog context vars
    for the duration of every request so all log events carry those fields.
    Echoes X-Correlation-ID back in the response.
    """

    def __init__(self, app: ASGIApp, server_id: str) -> None:
        super().__init__(app)
        self._server_id = server_id

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", "")
        user_id = request.headers.get("X-User-ID", "anonymous")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            user_id=user_id,
            server_id=self._server_id,
        )

        response = await call_next(request)

        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id

        return response


# ── Main MCPApp wrapper ───────────────────────────────────────────────────────

class MCPApp:
    """Wrapper around a FastAPI instance with JSON-RPC 2.0 dispatching."""

    def __init__(
        self,
        server_id: str,
        version: str,
        *,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.server_id = server_id
        self.version = version
        self._request_timeout = request_timeout
        self._tools: dict[str, _ToolHandler] = {}
        self._app = self._build_app()

        self._rpc_requests = Counter(
            f"mcp_{server_id}_rpc_requests_total",
            "Total JSON-RPC requests by method and status",
            ["method", "status"],
        )
        self._rpc_duration = Histogram(
            f"mcp_{server_id}_rpc_duration_seconds",
            "JSON-RPC handler latency in seconds",
            ["method"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def register_tool(self, name: str) -> Callable[[_ToolHandler], _ToolHandler]:
        """Decorator: register an async handler for a JSON-RPC method name."""

        def decorator(fn: _ToolHandler) -> _ToolHandler:
            self._tools[name] = fn
            return fn

        return decorator

    @property
    def app(self) -> FastAPI:
        return self._app

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            _configure_logging()
            _configure_sentry()
            _configure_tracing(self.server_id)
            logger.info("mcp_server.started", server_id=self.server_id, version=self.version)
            yield
            logger.info("mcp_server.stopped", server_id=self.server_id)

        app = FastAPI(
            title=f"MCP {self.server_id.replace('_', ' ').title()} Server",
            version=self.version,
            docs_url=None,
            redoc_url=None,
            lifespan=lifespan,
        )

        # Correlation ID middleware (outermost — runs on every request)
        app.add_middleware(CorrelationIdMiddleware, server_id=self.server_id)

        @app.get("/livez", include_in_schema=False)
        async def livez() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/readyz", include_in_schema=False)
        async def readyz() -> dict[str, str]:
            return {"status": "ok", "server_id": self.server_id}

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        @app.post("/", include_in_schema=False)
        async def dispatch(request: Request) -> JSONResponse:
            return await self._dispatch(request)

        return app

    async def _dispatch(self, request: Request) -> JSONResponse:
        request_id: str | int | None = None
        method: str = ""

        try:
            body = await request.body()
            try:
                payload: dict[str, Any] = json.loads(body)
            except json.JSONDecodeError:
                return JSONResponse(
                    make_error_response(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error"),
                    status_code=200,
                )

            request_id = payload.get("id")
            method = str(payload.get("method", ""))
            params: dict[str, Any] = payload.get("params") or {}

            if payload.get("jsonrpc") != "2.0" or not method:
                return JSONResponse(
                    make_error_response(
                        request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0 request"
                    ),
                    status_code=200,
                )

            handler = self._tools.get(method)
            if handler is None:
                self._rpc_requests.labels(method=method, status="not_found").inc()
                return JSONResponse(
                    make_error_response(
                        request_id,
                        JsonRpcErrorCode.METHOD_NOT_FOUND,
                        f"Method '{method}' not found",
                    ),
                    status_code=200,
                )

            # ── W3C traceparent extraction — makes tool spans child of agent span ──
            _attach_trace_context(request)

            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    handler(params, request),
                    timeout=self._request_timeout,
                )
                latency = time.monotonic() - t0
                self._rpc_requests.labels(method=method, status="ok").inc()
                self._rpc_duration.labels(method=method).observe(latency)
                logger.info(
                    "mcp.tool_call_ok",
                    server_id=self.server_id,
                    method=method,
                    latency_ms=int(latency * 1000),
                )
                return JSONResponse(make_success_response(request_id, result))

            except asyncio.TimeoutError:
                latency = time.monotonic() - t0
                self._rpc_requests.labels(method=method, status="timeout").inc()
                self._rpc_duration.labels(method=method).observe(latency)
                logger.error(
                    "mcp.tool_call_timeout",
                    server_id=self.server_id,
                    method=method,
                    timeout_s=self._request_timeout,
                )
                return JSONResponse(
                    make_error_response(
                        request_id,
                        JsonRpcErrorCode.TOOL_TIMEOUT,
                        f"Tool '{method}' timed out after {self._request_timeout}s",
                    )
                )

            except JsonRpcError as exc:
                latency = time.monotonic() - t0
                self._rpc_requests.labels(method=method, status="rpc_error").inc()
                self._rpc_duration.labels(method=method).observe(latency)
                logger.warning(
                    "mcp.tool_call_rpc_error",
                    server_id=self.server_id,
                    method=method,
                    code=exc.code,
                    error=exc.message,
                )
                return JSONResponse(
                    make_error_response(request_id, exc.code, exc.message, exc.data)
                )

        except Exception as exc:
            self._rpc_requests.labels(method=method or "unknown", status="internal_error").inc()
            _capture_exception(exc)
            logger.error(
                "mcp.tool_call_internal_error",
                server_id=self.server_id,
                method=method,
                error=str(exc),
                exc_info=True,
            )
            return JSONResponse(
                make_error_response(
                    request_id,
                    JsonRpcErrorCode.INTERNAL_ERROR,
                    "Internal server error",
                )
            )


# ── Sentry capture helper ─────────────────────────────────────────────────────


def _capture_exception(exc: BaseException) -> None:
    """Forward an unhandled exception to Sentry.

    Called explicitly for exceptions caught-and-swallowed inside the JSON-RPC
    dispatcher, which never reach the Starlette error handler that the Sentry
    FastAPI integration hooks into.
    """
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass


# ── Logging / tracing / Sentry setup ─────────────────────────────────────────


def _configure_logging() -> None:
    env = os.getenv("ENVIRONMENT", "development")
    log_level_name = os.getenv("LOG_LEVEL", "INFO")
    log_level = getattr(logging, log_level_name, logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderers: list[structlog.types.Processor] = (
        [structlog.dev.ConsoleRenderer(colors=True)]
        if env == "development"
        else [structlog.processors.JSONRenderer()]
    )
    structlog.configure(
        processors=[*shared_processors, *renderers],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENVIRONMENT", "development"),
            integrations=[
                StarletteIntegration(transaction_style="url"),
                FastApiIntegration(transaction_style="url"),
                AsyncioIntegration(),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
            send_default_pii=False,
        )
        logger.info("sentry.initialised", dsn_prefix=dsn[:20] + "...")
    except ImportError:
        logger.warning("sentry.sdk_not_installed", hint="pip install sentry-sdk[fastapi]")


def _configure_tracing(server_id: str) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create(
            {"service.name": f"mcp-{server_id}", "service.version": "0.1.0"}
        )
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        elif os.getenv("ENVIRONMENT", "development") == "development":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
    except ImportError:
        pass


def _attach_trace_context(request: Request) -> None:
    """Extract W3C traceparent from incoming headers and attach to current OTel context.

    This makes any span created inside the tool handler a child of the agent's
    span, enabling end-to-end distributed traces across the agent→MCP boundary.
    """
    try:
        from opentelemetry import context as otel_context, propagate

        carrier = dict(request.headers)
        ctx = propagate.extract(carrier)
        # attach() returns a token; we intentionally don't detach here because
        # the context lasts for the duration of this async task naturally via
        # Python contextvars. The handler coroutine inherits it.
        otel_context.attach(ctx)
    except Exception:
        pass  # Tracing must never break the request path
