"""LinkedIn Profile MCP Server — entry point.

Exposes three JSON-RPC 2.0 methods:
  fetch_profile         — fetch a LinkedIn profile by URL (RapidAPI, user-authed)
  normalize_job_title   — canonical title mapping (in-process, always available)
  suggest_connections   — people search for relevant connections (RapidAPI)

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Run (from mcp-servers/linkedin-profile/):
    uvicorn server:app --host 0.0.0.0 --port 3008
"""
from __future__ import annotations

import os
import sys

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request

from clients.linkedin_profile_client import LinkedInProfileClient
from config import get_settings
from tools.fetch_profile import handle_fetch_profile
from tools.normalize_job_title import handle_normalize_job_title
from tools.suggest_connections import handle_suggest_connections
from shared.auth import verify_api_key
from shared.base_server import _configure_logging, _configure_sentry, _configure_tracing, CorrelationIdMiddleware
from shared.cache import ResponseCache
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()

_client: LinkedInProfileClient | None = None
_cache: ResponseCache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter: RateLimiter = RateLimiter(redis_url=_settings.redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_sentry()
    _configure_tracing("linkedin_profile")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("linkedin_profile.redis_connected")
    except Exception as exc:
        logger.warning("linkedin_profile.redis_unavailable", error=str(exc))

    global _client
    if _settings.linkedin_api_key:
        _client = LinkedInProfileClient(
            api_key=_settings.linkedin_api_key.get_secret_value(),
            api_host=_settings.linkedin_api_host,
            timeout_seconds=_settings.http_timeout_seconds,
            max_retries=_settings.http_max_retries,
        )
        logger.info("linkedin_profile.api_client_registered")
    else:
        logger.info(
            "linkedin_profile.api_client_skipped",
            hint="Set LINKEDIN_API_KEY to enable profile fetch and connection suggestions",
        )
    logger.info(
        "linkedin_profile.normalizer_ready",
        hint="normalize_job_title is always available (in-process, no API key required)",
    )

    yield

    await _cache.close()
    await _rate_limiter.close()
    logger.info("linkedin_profile.shutdown")


app = FastAPI(
    title="MCP LinkedIn Profile Server",
    version="0.1.0",
    description="JSON-RPC 2.0 LinkedIn profile tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Correlation-ID middleware — binds structlog context vars per request
app.add_middleware(CorrelationIdMiddleware, server_id="linkedin_profile")


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    redis_ok = await _cache.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "server_id": "linkedin_profile",
        "api_client": "configured" if _client else "unconfigured",
        "normalizer": "ready",
        "checks": {"redis": "ok" if redis_ok else "unavailable"},
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/", include_in_schema=False)
async def rpc_endpoint(request: Request):
    import json

    from fastapi.responses import JSONResponse

    from shared.base_server import _attach_trace_context
    from shared.error_handler import (
        JsonRpcError,
        JsonRpcErrorCode,
        make_error_response,
        make_success_response,
    )

    request_id = None
    method = ""
    try:
        body = await request.body()
        try:
            payload: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse(make_error_response(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error"))

        request_id = payload.get("id")
        method = str(payload.get("method", ""))
        params: dict[str, Any] = payload.get("params") or {}

        if payload.get("jsonrpc") != "2.0" or not method:
            return JSONResponse(
                make_error_response(request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0 request")
            )

        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))
        _attach_trace_context(request)

        common = dict(
            params=params,
            request=request,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
        )

        if method == "fetch_profile":
            result = await handle_fetch_profile(client=_client, **common)
        elif method == "normalize_job_title":
            result = await handle_normalize_job_title(params=params, request=request)
        elif method == "suggest_connections":
            result = await handle_suggest_connections(client=_client, **common)
        else:
            return JSONResponse(
                make_error_response(request_id, JsonRpcErrorCode.METHOD_NOT_FOUND, f"Method '{method}' not found")
            )

        return JSONResponse(make_success_response(request_id, result))

    except JsonRpcError as exc:
        return JSONResponse(make_error_response(request_id, exc.code, exc.message, exc.data))
    except Exception as exc:
        logger.error("rpc.unhandled_error", method=method, error=str(exc), exc_info=True)
        return JSONResponse(
            make_error_response(request_id, JsonRpcErrorCode.INTERNAL_ERROR, "Internal server error")
        )


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
