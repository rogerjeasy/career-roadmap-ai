"""Shared pytest fixtures for the centralised ``apps/api/tests`` suite.

This file is imported by pytest before any test module is collected, so the
environment safety-net below runs *before* ``src.config`` is imported. That
guarantees ``Settings`` can be constructed even on a machine (or CI runner)
without a populated ``.env`` — the required secrets get harmless placeholder
values when they are not already set.

The fixtures here are deliberately I/O-free: every external dependency
(Firestore, Redis, the HTTP client, push, the LLM) is a mock. Integration
tests build small FastAPI apps via :func:`make_app` and override the relevant
FastAPI dependencies rather than spinning up real infrastructure.
"""
from __future__ import annotations

import os

# ── Environment safety-net (must run before any ``src`` import) ────────────────
# Only fills values that are missing so a real local ``.env`` always wins.
_DEFAULT_ENV: dict[str, str] = {
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "ENVIRONMENT": "development",
    "PROMETHEUS_METRICS_ENABLED": "false",
    "OTEL_TRACING_ENABLED": "false",
}
for _key, _value in _DEFAULT_ENV.items():
    os.environ.setdefault(_key, _value)

from collections.abc import Callable, Iterator  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.requests import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.core.auth import AuthenticatedUser, get_current_user  # noqa: E402
from src.core.exceptions import AppException  # noqa: E402
from src.core.middleware import CaseConversionMiddleware  # noqa: E402


# ── Auth fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def user() -> AuthenticatedUser:
    """A plain authenticated end-user."""
    return AuthenticatedUser(
        uid="user-123",
        email="test@example.com",
        email_verified=True,
        name="Test User",
        sign_in_provider="password",
    )


@pytest.fixture
def admin_user() -> AuthenticatedUser:
    """An authenticated admin."""
    return AuthenticatedUser(
        uid="admin-1",
        email="admin@example.com",
        email_verified=True,
        name="Admin",
        sign_in_provider="password",
        role="admin",
    )


# ── App-building helpers ───────────────────────────────────────────────────────


def _register_app_exception_handler(app: FastAPI) -> None:
    """Mirror the global AppException → JSON translation from ``src.main``."""

    @app.exception_handler(AppException)
    async def _handler(_request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "detail": exc.detail},
        )


@pytest.fixture
def make_app() -> Callable[..., FastAPI]:
    """Factory that assembles a minimal FastAPI app around a router.

    It reproduces the parts of ``src.main`` that matter for request/response
    behaviour — the ``AppException`` handler and (optionally) the
    case-conversion middleware — without the lifespan, observability, or
    Firebase wiring that needs live infrastructure.

    Example::

        app = make_app(router=user_router, overrides={get_user_service: lambda: svc})
        client = TestClient(app)
    """

    def _factory(
        *,
        router: Any | None = None,
        overrides: dict[Any, Any] | None = None,
        case_conversion: bool = False,
        current_user: AuthenticatedUser | None = None,
    ) -> FastAPI:
        app = FastAPI()
        _register_app_exception_handler(app)
        if case_conversion:
            app.add_middleware(CaseConversionMiddleware)
        if router is not None:
            app.include_router(router)
        if current_user is not None:
            app.dependency_overrides[get_current_user] = lambda: current_user
        for dep, replacement in (overrides or {}).items():
            app.dependency_overrides[dep] = replacement
        return app

    return _factory


@pytest.fixture
def client_factory(make_app: Callable[..., FastAPI]) -> Callable[..., TestClient]:
    """Build a TestClient for an app produced by :func:`make_app`.

    The client is created *without* the ``with`` context manager so the app's
    lifespan (Redis pool, Firebase init) never runs — every dependency the
    handler needs is supplied through ``overrides`` instead.
    """

    def _factory(**kwargs: Any) -> TestClient:
        return TestClient(make_app(**kwargs), raise_server_exceptions=True)

    return _factory


# ── Generic mock repositories / services ───────────────────────────────────────


@pytest.fixture
def mock_repo() -> MagicMock:
    """A repository whose every method is an ``AsyncMock``."""
    repo = MagicMock()
    for method in ("get", "list", "create", "update", "delete", "iter_all"):
        setattr(repo, method, AsyncMock())
    return repo


@pytest.fixture
def mock_push() -> MagicMock:
    push = MagicMock()
    push.send_to_user = AsyncMock()
    return push


@pytest.fixture
def anyio_backend() -> str:
    """Pin AnyIO-driven async fixtures to asyncio (TestClient uses it)."""
    return "asyncio"
