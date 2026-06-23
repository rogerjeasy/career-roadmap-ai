"""Integration test for the liveness probe.

``/livez`` has no dependencies, so it is mounted on a bare app and called over
HTTP. (``/readyz`` deliberately touches the database and is covered separately
where a DB is available.)
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.healthcheck import router as health_router

pytestmark = pytest.mark.integration


def test_livez_returns_alive() -> None:
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}
