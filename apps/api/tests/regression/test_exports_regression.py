"""Regression tests for the Exports domain."""
import pytest
from fastapi.testclient import TestClient

from src.domains.exports.service import get_export_service
from src.endpoints.v1.exports_controller import router

pytestmark = pytest.mark.regression


class FakeExportService:
    async def roadmap_markdown(self, uid, roadmap_id):
        return "# Café résumé — 100% ✅\n"  # unicode must survive the response

    async def roadmap_ics(self, uid, roadmap_id):
        return "BEGIN:VCALENDAR\n"


def test_export_is_served_as_a_download_with_utf8(make_app, user) -> None:
    # REGRESSION: exports must be attachments (download), not inline, and must
    # preserve UTF-8 content exactly so accented/emoji roadmap text isn't mangled.
    app = make_app(router=router, overrides={get_export_service: lambda: FakeExportService()}, current_user=user)
    client = TestClient(app)
    resp = client.get("/exports/roadmap/r1/markdown")
    assert 'filename="roadmap.md"' in resp.headers["content-disposition"]
    assert "charset=utf-8" in resp.headers["content-type"]
    assert "Café résumé — 100% ✅" in resp.text


def test_ics_filename_is_dot_ics(make_app, user) -> None:
    app = make_app(router=router, overrides={get_export_service: lambda: FakeExportService()}, current_user=user)
    client = TestClient(app)
    resp = client.get("/exports/roadmap/r1/ics")
    assert 'filename="roadmap.ics"' in resp.headers["content-disposition"]
