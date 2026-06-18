"""Unit tests for the localisation service (cache + generate + fallback)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domains.localisation.schemas import report_slug
from src.domains.localisation.service import LocalisationService

_LLM_PAYLOAD = {
    "summary": "Strong market for this role.",
    "salary": {"currency": "EUR", "low": 70000, "median": 90000, "high": 115000, "note": "Berlin rates."},
    "cost_of_living": "Moderate vs salary.",
    "visa_pathways": [{"name": "EU Blue Card", "summary": "For degree holders.", "difficulty": "moderate"}],
    "language_requirements": "English is fine in tech; German helps.",
    "hiring_culture": ["Structured interviews."],
    "networking_channels": ["Local meetups."],
    "relocation_steps": ["Secure an offer", "Apply for the Blue Card"],
    "confidence": 0.7,
    "assumptions": ["Rates vary by city."],
}


def _fake_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get.return_value = None
    repo.create.side_effect = lambda user_id, data, doc_id=None: {"id": doc_id, **data}
    repo.update.side_effect = lambda doc_id, user_id, data: {"id": doc_id, **data}
    repo.list_for_user.return_value = []
    repo.hard_delete.return_value = True
    return repo


def _fake_llm(payload=_LLM_PAYLOAD) -> AsyncMock:
    llm = AsyncMock()
    llm.complete_json.return_value = payload
    return llm


def test_report_slug_is_deterministic_and_safe() -> None:
    a = report_slug("Germany", "ML Engineer")
    b = report_slug("germany", "ml engineer")
    assert a == b == "germany-ml-engineer"


@pytest.mark.asyncio
async def test_get_report_generates_and_caches_on_miss() -> None:
    repo, llm = _fake_repo(), _fake_llm()
    svc = LocalisationService(repo, llm)

    report = await svc.get_report("u1", "Germany", "ML Engineer")

    llm.complete_json.assert_awaited_once()
    repo.create.assert_awaited_once()
    assert report.country == "Germany"
    assert report.role == "ML Engineer"
    assert report.salary.currency == "EUR"
    assert report.confidence == 0.7


@pytest.mark.asyncio
async def test_get_report_returns_cache_without_llm() -> None:
    repo, llm = _fake_repo(), _fake_llm()
    repo.get.return_value = {
        "id": "germany-ml-engineer", "country": "Germany", "role": "ML Engineer",
        "confidence": 0.6, "salary": {"currency": "EUR"},
    }
    svc = LocalisationService(repo, llm)

    report = await svc.get_report("u1", "Germany", "ML Engineer")

    llm.complete_json.assert_not_awaited()
    assert report.confidence == 0.6


@pytest.mark.asyncio
async def test_refresh_regenerates_even_when_cached() -> None:
    repo, llm = _fake_repo(), _fake_llm()
    repo.get.return_value = {"id": "germany-ml-engineer", "country": "Germany", "role": "ML Engineer"}
    svc = LocalisationService(repo, llm)

    await svc.get_report("u1", "Germany", "ML Engineer", refresh=True)

    llm.complete_json.assert_awaited_once()
    repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_falls_back_on_bad_llm_output() -> None:
    repo = _fake_repo()
    llm = AsyncMock()
    llm.complete_json.side_effect = ValueError("bad json")
    svc = LocalisationService(repo, llm)

    report = await svc.get_report("u1", "Japan", "Designer")

    assert report.confidence == 0.0
    assert report.country == "Japan"
    assert report.assumptions  # carries an honest limitation note
