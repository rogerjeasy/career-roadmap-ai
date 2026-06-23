"""Integration tests for the Exports controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.exports.service import get_export_service
from src.endpoints.v1.exports_controller import router

pytestmark = pytest.mark.integration


class FakeExportService:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists

    async def roadmap_markdown(self, uid, roadmap_id):
        if not self.exists:
            raise NotFoundError("Roadmap not found.")
        return "# My Roadmap\n\n- Phase 1\n"

    async def roadmap_ics(self, uid, roadmap_id):
        if not self.exists:
            raise NotFoundError("Roadmap not found.")
        return "BEGIN:VCALENDAR\nEND:VCALENDAR\n"


def _client(make_app, user, exists: bool = True) -> TestClient:
    app = make_app(
        router=router,
        overrides={get_export_service: lambda: FakeExportService(exists)},
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_markdown_export(make_app, user) -> None:
    client = _client(make_app, user)
    resp = client.get("/exports/roadmap/r1/markdown")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text.startswith("# My Roadmap")


def test_ics_export(make_app, user) -> None:
    client = _client(make_app, user)
    resp = client.get("/exports/roadmap/r1/ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert resp.text.startswith("BEGIN:VCALENDAR")


def test_missing_roadmap_returns_404(make_app, user) -> None:
    client = _client(make_app, user, exists=False)
    assert client.get("/exports/roadmap/nope/markdown").status_code == 404
    assert client.get("/exports/roadmap/nope/ics").status_code == 404
