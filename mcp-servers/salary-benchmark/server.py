"""Salary Benchmark MCP Server — entry point.

Exposes one JSON-RPC 2.0 method:
  get_salary_range — salary percentiles for a role + country + experience level

Data sources (registered only when API keys are present):
  - Glassdoor (RapidAPI) — live salary estimates
  - levels.fyi — crowd-sourced compensation data (no key required)
  - Curated dataset — Swiss/EU AI-ML roles (always available as fallback)

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Run (from mcp-servers/salary-benchmark/):
    uvicorn server:app --host 0.0.0.0 --port 3003
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

from clients.base_client import BaseSalaryClient
from clients.glassdoor_salary_client import GlassdoorSalaryClient
from clients.levels_fyi_client import LevelsFyiClient
from config import get_settings
from tools.get_salary_range import handle_get_salary_range
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

_clients: dict[str, BaseSalaryClient] = {}
_cache: ResponseCache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter: RateLimiter = RateLimiter(redis_url=_settings.redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_sentry()
    _configure_tracing("salary_benchmark")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("salary_benchmark.redis_connected")
    except Exception as exc:
        logger.warning("salary_benchmark.redis_unavailable", error=str(exc))

    global _clients
    _clients = _build_clients()
    logger.info(
        "salary_benchmark.clients_registered",
        sources=list(_clients.keys()),
    )

    yield

    await _cache.close()
    await _rate_limiter.close()
    logger.info("salary_benchmark.shutdown")


def _build_clients() -> dict[str, BaseSalaryClient]:
    clients: dict[str, BaseSalaryClient] = {}
    timeout = _settings.http_timeout_seconds
    retries = _settings.http_max_retries

    if _settings.glassdoor_api_key:
        clients["glassdoor"] = GlassdoorSalaryClient(
            api_key=_settings.glassdoor_api_key.get_secret_value(),
            api_host=_settings.glassdoor_api_host,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("salary_benchmark.client_registered", source="Glassdoor")

    if _settings.levels_fyi_enabled:
        clients["levels_fyi"] = LevelsFyiClient(
            base_url=_settings.levels_fyi_base_url,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("salary_benchmark.client_registered", source="levels.fyi")

    if not clients:
        logger.info(
            "salary_benchmark.curated_only_mode",
            hint="Set GLASSDOOR_API_KEY for live salary data",
        )

    return clients


app = FastAPI(
    title="MCP Salary Benchmark Server",
    version="0.1.0",
    description="JSON-RPC 2.0 salary benchmark tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, server_id="salary_benchmark")


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    redis_ok = await _cache.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "server_id": "salary_benchmark",
        "sources": list(_clients.keys()) + ["curated_dataset"],
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
                make_error_response(request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0 request")
            )

        verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))
        _attach_trace_context(request)

        if method == "get_salary_range":
            result = await handle_get_salary_range(
                params=params,
                request=request,
                clients=_clients,
                cache=_cache,
                rate_limiter=_rate_limiter,
                rate_limit=_settings.rate_limit_per_minute,
            )
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
