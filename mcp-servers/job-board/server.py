"""Job Board MCP Server — entry point.

Exposes three JSON-RPC 2.0 methods:
  search_jobs         — multi-source job search
  get_job_detail      — full detail for a specific posting
  get_trending_roles  — market trending role list

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Configuration is loaded from environment variables via ``JobBoardSettings``.
API keys for each source are optional — sources without credentials are
silently skipped at startup.

Run (from mcp-servers/job-board/):
    uvicorn server:app --host 0.0.0.0 --port 3001

Or via the Poetry script:
    poetry run start
"""
from __future__ import annotations

import os
import sys

# Add mcp-servers/ parent directory to sys.path so that `shared` is importable.
# This file lives at mcp-servers/job-board/server.py; parent = mcp-servers/.
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request

from clients.base_client import BaseJobBoardClient
from clients.glassdoor_client import GlassdoorClient
from clients.indeed_client import IndeedClient
from clients.linkedin_client import LinkedInClient
from clients.swiss_jobs_client import SwissJobsClient
from config import get_settings
from tools.get_job_detail import handle_get_job_detail
from tools.get_trending_roles import handle_get_trending_roles
from tools.search_jobs import handle_search_jobs
from shared.auth import verify_api_key
from shared.base_server import MCPApp, _configure_logging, _configure_tracing
from shared.cache import ResponseCache
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()

# ── Server state (injected at startup) ───────────────────────────────────────

_clients: dict[str, BaseJobBoardClient] = {}
_cache: ResponseCache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter: RateLimiter = RateLimiter(redis_url=_settings.redis_url)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_tracing("job_board")

    # ── Initialise Redis ──────────────────────────────────────────────────
    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("job_board.redis_connected", url=_settings.redis_url)
    except Exception as exc:
        logger.warning("job_board.redis_unavailable", error=str(exc))

    # ── Register job board clients ────────────────────────────────────────
    global _clients
    _clients = _build_clients()
    if not _clients:
        logger.warning(
            "job_board.no_clients_configured",
            hint="Set LINKEDIN_API_KEY, INDEED_API_KEY, or GLASSDOOR_API_KEY env vars",
        )
    else:
        logger.info(
            "job_board.clients_registered",
            sources=[c.source.value for c in _clients.values()],
        )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    for client in _clients.values():
        # Clients use context manager protocol; exit them if they were entered
        pass
    await _cache.close()
    await _rate_limiter.close()
    logger.info("job_board.shutdown")


def _build_clients() -> dict[str, BaseJobBoardClient]:
    clients: dict[str, BaseJobBoardClient] = {}
    timeout = _settings.http_timeout_seconds
    retries = _settings.http_max_retries

    if _settings.linkedin_api_key:
        key = _settings.linkedin_api_key.get_secret_value()
        clients["linkedin"] = LinkedInClient(
            api_key=key,
            api_host=_settings.linkedin_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("job_board.client_registered", source="LinkedIn")

    if _settings.indeed_api_key:
        key = _settings.indeed_api_key.get_secret_value()
        clients["indeed"] = IndeedClient(
            api_key=key,
            api_host=_settings.indeed_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("job_board.client_registered", source="Indeed")

    if _settings.glassdoor_api_key:
        key = _settings.glassdoor_api_key.get_secret_value()
        clients["glassdoor"] = GlassdoorClient(
            api_key=key,
            api_host=_settings.glassdoor_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("job_board.client_registered", source="Glassdoor")

    # Swiss Jobs requires no API key — always registered
    clients["swiss_jobs"] = SwissJobsClient(
        timeout_seconds=timeout,
        max_retries=retries,
    )
    logger.info("job_board.client_registered", source="Swiss Jobs (jobs.ch / jobup.ch)")

    return clients


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCP Job Board Server",
    version="0.1.0",
    description="JSON-RPC 2.0 job board tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    return {
        "status": "ok",
        "server_id": "job_board",
        "sources": [c.source.value for c in _clients.values()],
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/", include_in_schema=False)
async def rpc_endpoint(request: Request):
    """JSON-RPC 2.0 dispatcher. Routes ``method`` to the registered tool handler."""
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

        # ── Auth (optional — bypassed when MCP_API_KEY not set) ───────────
        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))

        # ── Tool routing ──────────────────────────────────────────────────
        common_kwargs = dict(
            params=params,
            request=request,
            clients=_clients,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
        )

        if method == "search_jobs":
            result = await handle_search_jobs(**common_kwargs)
        elif method == "get_job_detail":
            result = await handle_get_job_detail(**common_kwargs)
        elif method == "get_trending_roles":
            result = await handle_get_trending_roles(**common_kwargs)
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


def main() -> None:
    import uvicorn

    uvicorn.run(
        "server:app",
        host=_settings.host,
        port=_settings.port,
        reload=_settings.environment == "development",
        log_level=_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
