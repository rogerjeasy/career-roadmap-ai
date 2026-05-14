"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from src.config import settings
from src.core.auth import init_firebase_app
from src.core.exceptions import AppException
from src.core.healthcheck import router as health_router
from src.core.logging import configure_logging, get_logger
from src.core.middleware import CaseConversionMiddleware, TraceContextMiddleware, setup_rate_limiter
from src.endpoints.v1 import router as api_v1_router
from src.endpoints.v1.stream_controller import router as stream_sse_router
from src.observability import setup_prometheus, setup_sentry, setup_tracing

# Init Sentry BEFORE the app so it captures startup errors.
setup_sentry()
configure_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Shared Redis connection pool (max_connections caps sockets under traffic spikes)
    pool = aioredis.ConnectionPool.from_url(
        str(settings.redis_url),
        decode_responses=True,
        max_connections=settings.redis_max_connections,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)

    # Shared async HTTP client (used by UserService for Firebase REST API calls)
    app.state.http_client = httpx.AsyncClient(timeout=10.0)

    # Firebase Admin SDK — idempotent, safe to call multiple times
    init_firebase_app()

    logger.info("api.startup", env=settings.environment, app=settings.app_name)
    yield

    await app.state.redis.aclose()
    await app.state.http_client.aclose()
    logger.info("api.shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Career Roadmap AI — agentic backend",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Observability
if settings.prometheus_metrics_enabled:
    setup_prometheus(app)
setup_tracing(app)

# Rate limiting — before CORS so 429 responses also carry CORS headers
setup_rate_limiter(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Case conversion — outermost layer so it sees every request first and every
# response last: camelCase→snake_case on the way in, snake_case→camelCase out.
app.add_middleware(CaseConversionMiddleware)

# Trace context — added last = runs outermost inside Starlette, just under the
# OTel ASGI wrapper. Binds trace_id/span_id into structlog for every log line.
app.add_middleware(TraceContextMiddleware)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Translate domain exceptions to JSON responses."""
    logger.warning(
        "app.exception",
        path=request.url.path,
        error_code=exc.error_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health_router)
app.include_router(api_v1_router)
# Registered at /stream/{session_id} (no /api/v1 prefix) so Kong's fastapi-sse
# service (response_buffering: false, 1-hour timeout) routes to it correctly.
app.include_router(stream_sse_router)


# ── Meta ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
