"""Course Catalogue MCP Server — entry point.

Exposes two JSON-RPC 2.0 methods:
  search_courses     — multi-source concurrent course search
  get_course_detail  — full detail for a specific course

Sources: Coursera (RapidAPI), Udemy (RapidAPI), edX (public), YouTube (v3), O'Reilly (RapidAPI)
Sources without credentials are silently skipped at startup.

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Run (from mcp-servers/course-catalogue/):
    uvicorn server:app --host 0.0.0.0 --port 3002

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

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request

from clients.base_client import BaseCourseClient
from clients.coursera_client import CourseraClient
from clients.edx_client import EdxClient
from clients.oreilly_client import OReillyClient
from clients.udemy_client import UdemyClient
from clients.youtube_client import YouTubeClient
from config import get_settings
from tools.get_course_detail import handle_get_course_detail
from tools.search_courses import handle_search_courses
from shared.auth import verify_api_key
from shared.base_server import _configure_logging, _configure_tracing
from shared.cache import ResponseCache
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()

# ── Server state ──────────────────────────────────────────────────────────────

_clients: dict[str, BaseCourseClient] = {}
_cache: ResponseCache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter: RateLimiter = RateLimiter(redis_url=_settings.redis_url)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_tracing("course_catalogue")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("course_catalogue.redis_connected", url=_settings.redis_url)
    except Exception as exc:
        logger.warning("course_catalogue.redis_unavailable", error=str(exc))

    global _clients
    _clients = _build_clients()
    if not _clients:
        logger.warning(
            "course_catalogue.no_clients_configured",
            hint="Set COURSERA_API_KEY, UDEMY_API_KEY, YOUTUBE_API_KEY, or OREILLY_API_KEY env vars",
        )
    else:
        logger.info(
            "course_catalogue.clients_registered",
            sources=[c.source.value for c in _clients.values()],
        )

    yield

    await _cache.close()
    await _rate_limiter.close()
    logger.info("course_catalogue.shutdown")


def _build_clients() -> dict[str, BaseCourseClient]:
    clients: dict[str, BaseCourseClient] = {}
    timeout = _settings.http_timeout_seconds
    retries = _settings.http_max_retries

    if _settings.coursera_api_key:
        clients["coursera"] = CourseraClient(
            api_key=_settings.coursera_api_key.get_secret_value(),
            api_host=_settings.coursera_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("course_catalogue.client_registered", source="Coursera")

    if _settings.udemy_api_key:
        clients["udemy"] = UdemyClient(
            api_key=_settings.udemy_api_key.get_secret_value(),
            api_host=_settings.udemy_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("course_catalogue.client_registered", source="Udemy")

    if _settings.youtube_api_key:
        clients["youtube"] = YouTubeClient(
            api_key=_settings.youtube_api_key.get_secret_value(),
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("course_catalogue.client_registered", source="YouTube")

    if _settings.oreilly_api_key:
        clients["oreilly"] = OReillyClient(
            api_key=_settings.oreilly_api_key.get_secret_value(),
            api_host=_settings.oreilly_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("course_catalogue.client_registered", source="O'Reilly")

    # edX requires no API key — always registered
    clients["edx"] = EdxClient(
        discovery_base_url=_settings.edx_discovery_url,
        timeout_seconds=timeout,
        max_retries=retries,
    )
    logger.info("course_catalogue.client_registered", source="edX (public)")

    return clients


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCP Course Catalogue Server",
    version="0.1.0",
    description="JSON-RPC 2.0 course catalogue tool server for Career Roadmap AI",
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
        "server_id": "course_catalogue",
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

        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))

        common_kwargs = dict(
            params=params,
            request=request,
            clients=_clients,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
        )

        if method == "search_courses":
            result = await handle_search_courses(**common_kwargs)
        elif method == "get_course_detail":
            result = await handle_get_course_detail(**common_kwargs)
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
