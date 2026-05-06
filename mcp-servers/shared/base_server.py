"""Base FastAPI application factory for all MCP tool servers.

Every MCP server extends this base:

1. Mounts a ``POST /`` JSON-RPC 2.0 dispatcher
2. Exposes ``GET /livez`` and ``GET /readyz`` health endpoints
3. Exposes ``GET /metrics`` for Prometheus scraping
4. Wires structured logging, OpenTelemetry, and Sentry on startup

Each server registers its tool handlers via ``register_tool``::

    app = create_mcp_app(server_id="job_board", version="0.1.0")

    @app.register_tool("search_jobs")
    async def search_jobs(params: dict, request: Request) -> dict:
        ...

The dispatcher at ``POST /`` routes ``method`` → registered handler.
"""
from __future__ import annotations

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

from shared.error_handler import (
    JsonRpcError,
    JsonRpcErrorCode,
    make_error_response,
    make_success_response,
)

_ToolHandler = Callable[..., Coroutine[Any, Any, dict[str, Any]]]

logger = structlog.get_logger(__name__)


class MCPApp:
    """Wrapper around a FastAPI instance with JSON-RPC 2.0 dispatching."""

    def __init__(self, server_id: str, version: str) -> None:
        self.server_id = server_id
        self.version = version
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

        @app.get("/livez", include_in_schema=False)
        async def livez() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/readyz", include_in_schema=False)
        async def readyz() -> dict[str, str]:
            return {"status": "ok", "server_id": self.server_id}

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )

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

            t0 = time.monotonic()
            try:
                result = await handler(params, request)
                latency = time.monotonic() - t0
                self._rpc_requests.labels(method=method, status="ok").inc()
                self._rpc_duration.labels(method=method).observe(latency)
                logger.info(
                    "mcp.tool_call_ok",
                    server_id=self.server_id,
                    method=method,
                    latency_ms=int(latency * 1000),
                    correlation_id=request.headers.get("X-Correlation-ID", ""),
                )
                return JSONResponse(make_success_response(request_id, result))
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


# ── Logging + tracing setup ───────────────────────────────────────────────────


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


def _configure_tracing(server_id: str) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({"service.name": f"mcp-{server_id}", "service.version": "0.1.0"})
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
