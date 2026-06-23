"""Integration tests for ``CaseConversionMiddleware`` end-to-end through ASGI.

A real (tiny) FastAPI app is mounted with the middleware so the request/response
key translation is exercised over an actual HTTP round-trip via TestClient.
"""
from typing import Any, Callable

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

pytestmark = pytest.mark.integration


class _Echo(BaseModel):
    display_name: str
    photo_url: str = ""


def _build(make_app: Callable[..., FastAPI]) -> FastAPI:
    app = make_app(case_conversion=True)

    @app.post("/echo")
    async def echo(body: _Echo) -> dict[str, Any]:
        # Handler sees snake_case; returns snake_case.
        return {"received_name": body.display_name, "received_photo_url": body.photo_url}

    @app.get("/query")
    async def query(user_id: str = "", page_size: int = 0) -> dict[str, Any]:
        return {"user_id": user_id, "page_size": page_size}

    return app


def test_request_body_camel_to_snake_and_response_snake_to_camel(make_app, client_factory):
    from fastapi.testclient import TestClient

    client = TestClient(_build(make_app))
    resp = client.post("/echo", json={"displayName": "Ada", "photoURL": "http://x/a.png"})
    assert resp.status_code == 200
    # Response keys are camelCased on the way out.
    assert resp.json() == {"receivedName": "Ada", "receivedPhotoUrl": "http://x/a.png"}


def test_query_param_keys_are_snake_cased(make_app):
    from fastapi.testclient import TestClient

    client = TestClient(_build(make_app))
    resp = client.get("/query", params={"userId": "u1", "pageSize": 25})
    assert resp.status_code == 200
    assert resp.json() == {"userId": "u1", "pageSize": 25}


def test_non_json_response_is_left_untouched(make_app):
    from fastapi.testclient import TestClient
    from fastapi.responses import PlainTextResponse

    app = make_app(case_conversion=True)

    @app.get("/plain")
    async def plain() -> PlainTextResponse:
        return PlainTextResponse("hello_world")

    client = TestClient(app)
    resp = client.get("/plain")
    assert resp.text == "hello_world"


def test_error_response_body_is_also_camelcased(make_app):
    """4xx JSON bodies pass through the same camelCasing path."""
    from fastapi.testclient import TestClient

    from src.core.exceptions import NotFoundError

    app = make_app(case_conversion=True)

    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("missing")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 404
    # error_code stays snake-less (single word) but the contract is camelCase keys.
    assert resp.json() == {"errorCode": "not_found", "detail": "missing"}
