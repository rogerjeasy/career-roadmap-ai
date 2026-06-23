"""Regression tests for ``CaseConversionMiddleware`` edge cases.

Each test pins a specific behaviour that, if it silently regressed, would break
production traffic in a way unit tests of the pure helpers would not catch.
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

pytestmark = pytest.mark.regression


def test_billing_webhook_request_body_is_left_raw(make_app):
    """REGRESSION: Stripe signs the exact request bytes. The middleware must NOT
    rewrite keys to snake_case for ``/api/v1/billing/webhook`` or the HMAC check
    downstream fails. The *response* may still be camelCased.
    """
    app = make_app(case_conversion=True)

    @app.post("/api/v1/billing/webhook")
    async def webhook(request: Request) -> JSONResponse:
        raw = await request.body()
        # If the middleware had converted keys, "someField" would become "some_field".
        body_preserved = b'"someField"' in raw
        return JSONResponse({"body_preserved": body_preserved})

    client = TestClient(app)
    resp = client.post("/api/v1/billing/webhook", json={"someField": "v"})
    assert resp.status_code == 200
    assert resp.json() == {"bodyPreserved": True}


def test_content_length_is_rebuilt_after_recasing(make_app):
    """REGRESSION: when key recasing changes the body length, Content-Length must
    be rewritten or the client truncates / hangs. Long keys make the delta large.
    """
    app = make_app(case_conversion=True)

    @app.get("/payload")
    async def payload() -> dict:
        # snake_case keys → camelCase shrinks each key by one byte per underscore.
        return {f"field_number_{i}": i for i in range(50)}

    client = TestClient(app)
    resp = client.get("/payload")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 50  # full body decoded — not truncated
    assert "fieldNumber0" in data
    assert int(resp.headers["content-length"]) == len(resp.content)


def test_empty_body_response_is_not_corrupted(make_app):
    """REGRESSION: a 204/empty JSON body must not crash the response sender."""
    app: FastAPI = make_app(case_conversion=True)

    @app.get("/empty")
    async def empty() -> JSONResponse:
        return JSONResponse(content=None, status_code=200)

    client = TestClient(app)
    resp = client.get("/empty")
    assert resp.status_code == 200
