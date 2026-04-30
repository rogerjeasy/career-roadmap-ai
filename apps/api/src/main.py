"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from src.config import settings
from src.core.exceptions import AppException
from src.core.healthcheck import router as health_router
from src.core.logging import configure_logging, get_logger
from src.observability import setup_prometheus, setup_sentry, setup_tracing

# Init Sentry BEFORE the app so it captures startup errors.
setup_sentry()
configure_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api.startup", env=settings.environment, app=settings.app_name)
    yield
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# Routers
app.include_router(health_router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }