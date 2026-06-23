"""Integration tests for the global AppException → JSON handler.

Verifies that domain exceptions raised inside a route are rendered as the
documented ``{"error_code": ..., "detail": ...}`` envelope with the right
HTTP status, exactly as ``src.main`` wires it.
"""
import pytest

from src.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("exc_factory", "status_code", "error_code"),
    [
        (lambda: NotFoundError("nope"), 404, "not_found"),
        (lambda: ValidationError("bad"), 422, "validation_error"),
        (lambda: AuthorizationError("denied"), 403, "forbidden"),
        (lambda: ConflictError("dup"), 409, "conflict"),
    ],
)
def test_domain_exception_is_translated(make_app, exc_factory, status_code, error_code):
    from fastapi.testclient import TestClient

    app = make_app()

    @app.get("/raise")
    async def raise_it() -> None:
        raise exc_factory()

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/raise")
    assert resp.status_code == status_code
    body = resp.json()
    assert body["error_code"] == error_code
    assert "detail" in body


def test_successful_route_is_unaffected(make_app):
    from fastapi.testclient import TestClient

    app = make_app()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.get("/ok")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
