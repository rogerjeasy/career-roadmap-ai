"""Social Signals MCP Server — entry point.

Exposes five JSON-RPC 2.0 methods:
  get_hackernews_signals  — HN top stories & Ask HN per tech stack
  get_reddit_signals      — Top Reddit posts from tech subreddits
  get_twitter_signals     — Recent tweets by stack (requires Bearer Token)
  get_devto_signals       — Top Dev.to articles by stack tag
  get_trending_topics     — Cross-source aggregated trending topics

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Sources with missing credentials are silently skipped at startup:
  - HackerNews  — always available (Algolia API, no key required)
  - Reddit      — always available (public JSON API, no key required)
  - Dev.to      — always available (public API; DEVTO_API_KEY optional)
  - Twitter/X   — requires TWITTER_BEARER_TOKEN

Run (from mcp-servers/social-signals/):
    uvicorn server:app --host 0.0.0.0 --port 3005

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

from clients.base_client import BaseSocialClient
from clients.devto_client import DevToClient
from clients.hackernews_client import HackerNewsClient
from clients.reddit_client import RedditClient
from clients.twitter_client import TwitterClient
from config import get_settings
from tools.get_devto_signals import handle_get_devto_signals
from tools.get_hackernews_signals import handle_get_hackernews_signals
from tools.get_reddit_signals import handle_get_reddit_signals
from tools.get_trending_topics import handle_get_trending_topics
from tools.get_twitter_signals import handle_get_twitter_signals
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

# ── Server state ──────────────────────────────────────────────────────────────

_clients: dict[str, BaseSocialClient] = {}
_cache = ResponseCache(
    redis_url=_settings.redis_url,
    default_ttl=_settings.cache_ttl_seconds,
)
_rate_limiter = RateLimiter(redis_url=_settings.redis_url)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _configure_sentry()
    _configure_tracing("social_signals")

    try:
        await _cache.connect()
        await _rate_limiter.connect()
        logger.info("social_signals.redis_connected", url=_settings.redis_url)
    except Exception as exc:
        logger.warning("social_signals.redis_unavailable", error=str(exc))

    global _clients
    _clients = _build_clients()
    logger.info(
        "social_signals.clients_registered",
        sources=list(_clients.keys()),
    )

    yield

    await _cache.close()
    await _rate_limiter.close()
    logger.info("social_signals.shutdown")


def _build_clients() -> dict[str, BaseSocialClient]:
    clients: dict[str, BaseSocialClient] = {}
    timeout = _settings.http_timeout_seconds
    retries = _settings.http_max_retries

    # HackerNews — always registered
    clients["hackernews"] = HackerNewsClient(
        min_score=_settings.hn_min_score,
        base_url=_settings.hn_base_url,
        timeout_seconds=timeout,
        max_retries=retries,
    )
    logger.info("social_signals.client_registered", source="HackerNews")

    # Reddit — always registered (public API)
    clients["reddit"] = RedditClient(
        user_agent=_settings.reddit_user_agent,
        timeout_seconds=timeout,
        max_retries=retries,
    )
    logger.info("social_signals.client_registered", source="Reddit")

    # Dev.to — always registered; API key is optional
    devto_key: str | None = None
    if _settings.devto_api_key:
        devto_key = _settings.devto_api_key.get_secret_value()
    clients["devto"] = DevToClient(
        api_key=devto_key,
        timeout_seconds=timeout,
        max_retries=retries,
    )
    logger.info("social_signals.client_registered", source="Dev.to", authenticated=devto_key is not None)

    # Twitter/X — registered only when Bearer Token is set
    if _settings.twitter_bearer_token:
        token = _settings.twitter_bearer_token.get_secret_value()
        clients["twitter"] = TwitterClient(
            bearer_token=token,
            timeout_seconds=timeout,
            max_retries=retries,
        )
        logger.info("social_signals.client_registered", source="Twitter/X")
    else:
        logger.info(
            "social_signals.client_skipped",
            source="Twitter/X",
            hint="Set TWITTER_BEARER_TOKEN to enable",
        )

    return clients


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCP Social Signals Server",
    version="0.1.0",
    description="JSON-RPC 2.0 social signals tool server for Career Roadmap AI",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, server_id="social_signals")


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, Any]:
    redis_ok = await _cache.ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "server_id": "social_signals",
        "sources": list(_clients.keys()),
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
        _attach_trace_context(request)

        common_kwargs = dict(
            params=params,
            request=request,
            clients=_clients,
            cache=_cache,
            rate_limiter=_rate_limiter,
            rate_limit=_settings.rate_limit_per_minute,
        )

        if method == "get_hackernews_signals":
            result = await handle_get_hackernews_signals(**common_kwargs)
        elif method == "get_reddit_signals":
            result = await handle_get_reddit_signals(**common_kwargs)
        elif method == "get_twitter_signals":
            result = await handle_get_twitter_signals(**common_kwargs)
        elif method == "get_devto_signals":
            result = await handle_get_devto_signals(**common_kwargs)
        elif method == "get_trending_topics":
            result = await handle_get_trending_topics(**common_kwargs)
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
