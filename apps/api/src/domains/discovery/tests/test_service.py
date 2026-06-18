"""Unit tests for the discovery service (context build + generate + cache)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.domains.discovery.service import DiscoveryService
from src.session.models import SessionData, UserProfileContext

_LLM_PAYLOAD = {
    "based_on": "Your backend experience and Python skills.",
    "confidence": 0.6,
    "paths": [
        {
            "title": "ML Engineer",
            "summary": "Apply ML in production.",
            "fit_score": 72,
            "effort_to_switch": "medium",
            "timeline_months": 12,
            "salary_currency": "USD",
            "salary_low": 120000,
            "salary_high": 180000,
            "growth_outlook": "Strong demand.",
            "key_skills_to_gain": ["PyTorch", "MLOps"],
            "transferable_strengths": ["Python", "APIs"],
            "sample_phases": [{"title": "Foundations", "duration_weeks": 6, "focus": "ML basics"}],
            "rationale": "Builds on your backend base.",
        }
    ],
}


def _session_with_profile(**profile_kwargs) -> SessionData:
    now = datetime.now(timezone.utc)
    return SessionData(
        user_id="u1",
        email="u@example.com",
        created_at=now,
        last_active_at=now,
        user_profile_context=UserProfileContext(**profile_kwargs),
    )


def _fake_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get.return_value = None
    repo.create.side_effect = lambda user_id, data, doc_id=None: {"id": doc_id, **data}
    repo.update.side_effect = lambda doc_id, user_id, data: {"id": doc_id, **data}
    return repo


@pytest.mark.asyncio
async def test_generate_produces_paths_from_profile() -> None:
    repo = _fake_repo()
    llm = AsyncMock()
    llm.complete_json.return_value = _LLM_PAYLOAD
    sessions = AsyncMock()
    sessions.get.return_value = _session_with_profile(
        current_role="Backend Engineer", skills=["Python", "FastAPI"], location="Berlin"
    )
    svc = DiscoveryService(repo, llm, sessions)

    result = await svc.generate("u1")

    llm.complete_json.assert_awaited_once()
    repo.create.assert_awaited_once()
    assert result.has_data is True
    assert result.paths[0].title == "ML Engineer"
    assert result.paths[0].fit_score == 72


@pytest.mark.asyncio
async def test_generate_without_profile_returns_empty() -> None:
    repo = _fake_repo()
    llm = AsyncMock()
    sessions = AsyncMock()
    sessions.get.return_value = None
    svc = DiscoveryService(repo, llm, sessions)

    result = await svc.generate("u1")

    llm.complete_json.assert_not_awaited()
    assert result.has_data is False
    assert result.paths == []


@pytest.mark.asyncio
async def test_generate_falls_back_on_bad_llm_output() -> None:
    repo = _fake_repo()
    llm = AsyncMock()
    llm.complete_json.side_effect = ValueError("bad json")
    sessions = AsyncMock()
    sessions.get.return_value = _session_with_profile(skills=["SQL"])
    svc = DiscoveryService(repo, llm, sessions)

    result = await svc.generate("u1")
    assert result.has_data is False


@pytest.mark.asyncio
async def test_get_returns_cached_result() -> None:
    repo = _fake_repo()
    repo.get.return_value = {"id": "u1", "paths": _LLM_PAYLOAD["paths"], "confidence": 0.6}
    svc = DiscoveryService(repo, AsyncMock(), AsyncMock())

    result = await svc.get("u1")
    assert result.has_data is True
    assert result.paths[0].title == "ML Engineer"
