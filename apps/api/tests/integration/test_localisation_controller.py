"""Integration tests for the Localisation controller."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.domains.localisation.schemas import LocalisationReport, LocalisationReportSummary
from src.domains.localisation.service import get_localisation_service
from src.endpoints.v1.localisation_controller import router
from src.session.manager import get_session_manager

pytestmark = pytest.mark.integration


class FakeLocalisationService:
    def __init__(self) -> None:
        self.saved: dict[str, LocalisationReport] = {}

    async def get_report(self, uid, country, role, *, refresh=False):
        rep = LocalisationReport(id=f"{country}-{role}".lower(), country=country, role=role, summary="ok", confidence=0.6)
        self.saved[rep.id] = rep
        return rep

    async def list_saved(self, uid, limit=30):
        return [LocalisationReportSummary(id=r.id, country=r.country, role=r.role, confidence=r.confidence) for r in self.saved.values()]

    async def delete(self, uid, report_id):
        return self.saved.pop(report_id, None) is not None


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeLocalisationService()
    mgr = MagicMock()
    mgr.get = AsyncMock(return_value=None)  # no session → no fallback role
    app = make_app(
        router=router,
        overrides={get_localisation_service: lambda: service, get_session_manager: lambda: mgr},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_get_report_with_explicit_role(client: TestClient) -> None:
    resp = client.get("/localisation", params={"country": "Germany", "role": "PM"})
    assert resp.status_code == 200
    assert resp.json()["country"] == "Germany"


def test_get_without_role_and_no_session_returns_422(client: TestClient) -> None:
    resp = client.get("/localisation", params={"country": "Germany"})
    assert resp.status_code == 422


def test_saved_and_delete(client: TestClient) -> None:
    rid = client.get("/localisation", params={"country": "Germany", "role": "PM"}).json()["id"]
    assert len(client.get("/localisation/saved").json()) == 1
    assert client.delete(f"/localisation/{rid}").status_code == 204


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete("/localisation/nope").status_code == 404


def test_get_requires_country(client: TestClient) -> None:
    assert client.get("/localisation").status_code == 422
