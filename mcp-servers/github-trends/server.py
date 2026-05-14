"""GitHub Trends MCP Server — entry point.

Exposes two JSON-RPC 2.0 methods:
  get_trending_repos      — repositories gaining momentum in a language
  get_good_first_issues   — beginner-friendly open-source issues

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Run (from mcp-servers/github-trends/):
    uvicorn server:app --host 0.0.0.0 --port 3004

GITHUB_TOKEN env var is optional but recommended — raises rate limit from
60 to 5000 requests/hr.
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

from clients.github_client import GitHubClient
from config import get_settings
from tools.get_good_first_issues import handle_get_good_first_issues
from tools.get_trending_repos import handle_get_trending_repos
from shared.auth import verify_api_key
from shared.base_server import (
    CorrelationIdMiddleware,
    _attach_trace_context,
    _configure_logging,
    _configure_sentry,
    _configure_tracing,
)
from shared.cache import ResponseCache
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()

_github: GitHubClient | None = None
_cache: ResponseCache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter: RateLimiter = RateLimiter(redis_url=_settings.redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_sentry()
    _configure_tracing("github_trends")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("github_trends.redis_connected")
    except Exception as exc:
        logger.warning("github_trends.redis_unavailable", error=str(exc))

    global _github
    token = _settings.github_token.get_secret_value() if _settings.github_token else None
    _github = GitHubClient(
        token=token,
        base_url=_settings.github_api_base_url,
        timeout_seconds=_settings.http_timeout_seconds,
        max_retries=_settings.http_max_retries,
    )
    auth_mode = "authenticated" if token else "unauthenticated (60 req/hr limit)"
    logger.info("github_trends.client_initialized", auth_mode=auth_mode)

    yield

    await _cache.close()
    await _rate_limiter.close()
    logger.info("github_trends.shutdown")


app = FastAPI(
    title="MCP GitHub Trends Server",
    version="0.1.0",
    description="JSON-RPC 2.0 GitHub trends tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, server_id="github_trends")


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    redis_ok = await _cache.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "server_id": "github_trends",
        "authenticated": _settings.github_token is not None,
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
                make_error_response(request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0")
            )

        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))
        _attach_trace_context(request)

        common = dict(
            params=params,
            request=request,
            github=_github,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
        )

        if method == "get_trending_repos":
            result = await handle_get_trending_repos(**common)
        elif method == "get_good_first_issues":
            result = await handle_get_good_first_issues(**common)
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
