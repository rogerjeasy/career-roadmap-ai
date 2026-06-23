"""Unit tests for LocalisationService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.localisation.schemas import LocalisationReport, report_slug
from src.domains.localisation.service import LocalisationService

pytestmark = pytest.mark.unit


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "summary": "Good market for PMs in Germany.",
        "salary": {"currency": "EUR", "low": 60000, "median": 80000, "high": 100000},
        "confidence": 0.6, "assumptions": ["rates vary by city"],
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock(side_effect=lambda uid, data, doc_id=None: {"id": doc_id, **data})
    r.update = AsyncMock(side_effect=lambda slug, uid, data: {"id": slug, **data})
    r.list_for_user = AsyncMock(return_value=[])
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, llm) -> LocalisationService:
    return LocalisationService(repo, llm)


def test_report_slug_is_deterministic_and_sanitised() -> None:
    assert report_slug("Germany", "Product Manager") == report_slug("germany", "product manager")
    assert report_slug("Germany", "PM") == "germany-pm"


async def test_get_report_returns_cache_when_present(service, repo, llm) -> None:
    repo.get = AsyncMock(return_value={"id": "germany-pm", "country": "Germany", "role": "PM", "summary": "cached"})
    out = await service.get_report("u1", "Germany", "PM")
    assert out.summary == "cached"
    llm.complete_json.assert_not_called()


async def test_get_report_generates_when_not_cached(service, repo, llm) -> None:
    out = await service.get_report("u1", "Germany", "PM")
    assert isinstance(out, LocalisationReport)
    assert out.salary.currency == "EUR"
    repo.create.assert_awaited_once()


async def test_refresh_regenerates_even_if_cached(service, repo, llm) -> None:
    repo.get = AsyncMock(return_value={"id": "germany-pm", "country": "Germany", "role": "PM", "summary": "old"})
    out = await service.get_report("u1", "Germany", "PM", refresh=True)
    llm.complete_json.assert_called_once()
    assert out.summary.startswith("Good market")


async def test_generate_llm_error_returns_low_confidence_fallback(service, repo, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    out = await service.get_report("u1", "Germany", "PM")
    assert out.confidence == 0.0
    assert out.assumptions  # explains the failure


async def test_delete_returns_repo_result(service, repo) -> None:
    assert await service.delete("u1", "germany-pm") is True
    repo.hard_delete = AsyncMock(return_value=False)
    assert await service.delete("u1", "missing") is False
