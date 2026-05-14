"""Calendar MCP Server — entry point.

Exposes three JSON-RPC 2.0 methods:
  create_event        — Create a single event (milestone, reminder, one-off task)
  create_weekly_tasks — Bulk-create a week's career roadmap tasks as calendar events
  list_upcoming       — List upcoming events within a time window

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Both providers are always registered and authenticate via per-request OAuth
Bearer tokens supplied by the calling agent. Providers without a valid token
will receive a 401/403 from the upstream API.

Run (from mcp-servers/calendar/):
    uvicorn server:app --host 0.0.0.0 --port 3006

Or via the Poetry script:
    poetry run start
"""
from __future__ import annotations

import os
import sys

# Add mcp-servers/ parent to sys.path so that `shared` is importable.
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

import json
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from clients.base_client import BaseCalendarClient
from clients.google_calendar_client import GoogleCalendarClient
from clients.outlook_client import OutlookClient
from config import get_settings
from models import CalendarProvider, StoreOAuthTokenParams
from token_store import CalendarTokenStore
from tools.create_event import handle_create_event
from tools.create_weekly_tasks import handle_create_weekly_tasks
from tools.list_upcoming import handle_list_upcoming
from shared.auth import verify_api_key
from shared.base_server import (
    CorrelationIdMiddleware,
    _attach_trace_context,
    _configure_logging,
    _configure_sentry,
    _configure_tracing,
)
from shared.cache import ResponseCache
from shared.error_handler import JsonRpcError, JsonRpcErrorCode, make_error_response, make_success_response
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()

# ── Server state ──────────────────────────────────────────────────────────────

_clients: dict[str, BaseCalendarClient] = {}
_cache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter = RateLimiter(redis_url=_settings.redis_url)
_token_store = CalendarTokenStore(
    redis_url=_settings.redis_url,
    encryption_key=(
        _settings.calendar_token_encryption_key.get_secret_value()
        if _settings.calendar_token_encryption_key else None
    ),
    google_client_id=(
        _settings.google_oauth_client_id.get_secret_value()
        if _settings.google_oauth_client_id else None
    ),
    google_client_secret=(
        _settings.google_oauth_client_secret.get_secret_value()
        if _settings.google_oauth_client_secret else None
    ),
    microsoft_client_id=(
        _settings.microsoft_oauth_client_id.get_secret_value()
        if _settings.microsoft_oauth_client_id else None
    ),
    microsoft_client_secret=(
        _settings.microsoft_oauth_client_secret.get_secret_value()
        if _settings.microsoft_oauth_client_secret else None
    ),
)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_sentry()
    _configure_tracing("calendar")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        await _token_store.connect()
        logger.info("calendar.redis_connected", url=_settings.redis_url)
    except Exception as exc:
        logger.warning("calendar.redis_unavailable", error=str(exc))

    global _clients
    _clients = _build_clients()
    logger.info("calendar.providers_registered", providers=list(_clients.keys()))

    yield

    await _cache.close()
    await _rate_limiter.close()
    await _token_store.close()
    logger.info("calendar.shutdown")


def _build_clients() -> dict[str, BaseCalendarClient]:
    clients: dict[str, BaseCalendarClient] = {}
    timeout = _settings.http_timeout_seconds
    retries = _settings.http_max_retries

    # Google Calendar — always registered; auth token supplied per-request
    clients[CalendarProvider.GOOGLE] = GoogleCalendarClient(
        timeout_seconds=timeout, max_retries=retries
    )
    logger.info("calendar.client_registered", provider="Google Calendar")

    # Outlook (Microsoft Graph) — always registered; auth token supplied per-request
    clients[CalendarProvider.OUTLOOK] = OutlookClient(
        timeout_seconds=timeout, max_retries=retries
    )
    logger.info("calendar.client_registered", provider="Outlook")

    return clients


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCP Calendar Server",
    version="0.1.0",
    description="JSON-RPC 2.0 calendar tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, server_id="calendar")


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    redis_ok = await _cache.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "server_id": "calendar",
        "providers": list(_clients.keys()),
        "checks": {"redis": "ok" if redis_ok else "unavailable"},
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/", include_in_schema=False)
async def rpc_endpoint(request: Request):
    """JSON-RPC 2.0 dispatcher."""
    request_id = None
    method = ""
    try:
        body = await request.body()
        try:
            payload: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse(
                make_error_response(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error")
            )

        request_id = payload.get("id")
        method = str(payload.get("method", ""))
        params: dict[str, Any] = payload.get("params") or {}

        if payload.get("jsonrpc") != "2.0" or not method:
            return JSONResponse(
                make_error_response(
                    request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0 request"
                )
            )

        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))
        _attach_trace_context(request)

        common_kwargs = dict(
            params=params,
            request=request,
            clients=_clients,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
            token_store=_token_store,
        )

        if method == "create_event":
            result = await handle_create_event(**common_kwargs)
        elif method == "create_weekly_tasks":
            result = await handle_create_weekly_tasks(**common_kwargs)
        elif method == "list_upcoming":
            result = await handle_list_upcoming(**common_kwargs)
        elif method == "store_oauth_token":
            result = await _handle_store_oauth_token(params, request)
        else:
            return JSONResponse(
                make_error_response(
                    request_id,
                    JsonRpcErrorCode.METHOD_NOT_FOUND,
                    f"Method '{method}' not found",
                )
            )

        return JSONResponse(make_success_response(request_id, result))

    except JsonRpcError as exc:
        return JSONResponse(make_error_response(request_id, exc.code, exc.message, exc.data))
    except Exception as exc:
        logger.error("rpc.unhandled_error", method=method, error=str(exc), exc_info=True)
        return JSONResponse(
            make_error_response(
                request_id,
                JsonRpcErrorCode.INTERNAL_ERROR,
                "Internal server error",
            )
        )


async def _handle_store_oauth_token(
    params: dict,
    request: Request,
) -> dict:
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from shared.error_handler import JsonRpcError, JsonRpcErrorCode

    user_id = request.headers.get("X-User-ID", "")
    if not user_id:
        raise JsonRpcError(JsonRpcErrorCode.UNAUTHORIZED, "X-User-ID header is required")

    try:
        p = StoreOAuthTokenParams(**params)
    except ValidationError as exc:
        raise JsonRpcError(
            JsonRpcErrorCode.INVALID_PARAMS,
            "Invalid store_oauth_token parameters",
            data=exc.errors(),
        )

    await _token_store.store(
        user_id=user_id,
        provider=p.provider.value,
        access_token=p.access_token,
        refresh_token=p.refresh_token,
        expires_in=p.expires_in,
    )
    logger.info(
        "store_oauth_token.completed",
        user_id=user_id,
        provider=p.provider.value,
    )
    return {
        "stored": True,
        "provider": p.provider.value,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    import os
    import uvicorn

    is_dev = _settings.environment == "development"
    workers = int(os.getenv("MCP_WORKERS", "1"))
    uvicorn.run(
        "server:app",
        host=_settings.host,
        port=_settings.port,
        reload=is_dev,
        workers=1 if is_dev else workers,
        log_level=_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
