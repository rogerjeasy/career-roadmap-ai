"""Unit tests for NewsletterService preference upsert logic.

The Firestore repository is replaced by an AsyncMock — no Firestore, no network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.newsletter.schemas import NewsletterPrefsOut, NewsletterPrefsUpdate
from src.domains.newsletter.service import NewsletterService
from src.session.models import SessionData, PlanContext, UserProfileContext


def _doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "u1",
        "subscribed": True,
        "frequency": "weekly",
        "topics": ["market_trends"],
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(over)
    return base


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=None)
    m.create = AsyncMock()
    m.update = AsyncMock()
    return m


@pytest.fixture
def digests() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=None)
    m.create = AsyncMock(side_effect=lambda user_id, data, doc_id=None: {"id": doc_id, **data})
    m.update = AsyncMock(side_effect=lambda doc_id, user_id, data: {"id": doc_id, **data})
    return m


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock()
    return m


@pytest.fixture
def sessions() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=None)
    return m


@pytest.fixture
def service(
    repo: MagicMock, digests: MagicMock, llm: MagicMock, sessions: MagicMock
) -> NewsletterService:
    return NewsletterService(repo, digests, llm, sessions)


@pytest.mark.asyncio
async def test_get_returns_defaults_when_absent(
    service: NewsletterService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=None)
    prefs = await service.get("u1")
    assert prefs.subscribed is False
    assert prefs.frequency == "weekly"
    assert prefs.topics == []


@pytest.mark.asyncio
async def test_get_maps_existing_doc(
    service: NewsletterService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=_doc(subscribed=True, frequency="monthly"))
    prefs = await service.get("u1")
    assert prefs.subscribed is True
    assert prefs.frequency == "monthly"
    assert prefs.topics == ["market_trends"]


@pytest.mark.asyncio
async def test_update_creates_under_user_doc_id_when_absent(
    service: NewsletterService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=_doc(subscribed=True, frequency="biweekly"))
    out = await service.update(
        "u1",
        NewsletterPrefsUpdate(subscribed=True, frequency="biweekly", topics=["roadmap_nudges"]),
    )
    assert out.subscribed is True
    repo.create.assert_awaited_once()
    _, kwargs = repo.create.call_args
    assert kwargs.get("doc_id") == "u1"
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_patches_when_present(
    service: NewsletterService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=_doc())
    repo.update = AsyncMock(return_value=_doc(subscribed=False))
    out = await service.update(
        "u1", NewsletterPrefsUpdate(subscribed=False, frequency="weekly", topics=[])
    )
    assert out.subscribed is False
    repo.update.assert_awaited_once()
    repo.create.assert_not_awaited()


def test_from_doc_coerces_unknown_frequency() -> None:
    prefs = NewsletterPrefsOut.from_doc(_doc(frequency="hourly"))
    assert prefs.frequency == "weekly"


# ── Digest generation ──────────────────────────────────────────────────────────

_DIGEST_PAYLOAD = {
    "period_label": "This week",
    "summary": "RAG systems are surging in your field.",
    "articles": [
        {"title": "Why RAG matters", "why": "Core to your target role", "url": None},
        {"title": "MLOps in 2026", "why": "Hiring signal", "url": "https://example.com"},
        {"title": "Vector DBs", "why": "Adjacent skill", "url": None},
    ],
    "people_to_follow": [
        {"name": "Jane Dev", "reason": "RAG thought leader", "handle": "@jane"},
        {"name": "Sam ML", "reason": "MLOps writer", "handle": None},
    ],
    "action_item": "Ship a small RAG demo this week.",
    "confidence": 0.6,
}


def _session(target_role: str | None = "ML Engineer", snapshot: dict | None = None) -> SessionData:
    now = datetime.now(timezone.utc)
    return SessionData(
        user_id="u1",
        email="u@example.com",
        created_at=now,
        last_active_at=now,
        user_profile_context=UserProfileContext(target_role=target_role),
        plan_context=PlanContext(snapshot=snapshot or {}),
    )


@pytest.mark.asyncio
async def test_generate_digest_writes_and_returns(
    service: NewsletterService, digests: MagicMock, llm: MagicMock, sessions: MagicMock
) -> None:
    sessions.get = AsyncMock(return_value=_session(snapshot={"market": {"market_summary": "Hot"}}))
    llm.complete_json = AsyncMock(return_value=_DIGEST_PAYLOAD)

    digest = await service.generate_digest("u1")

    llm.complete_json.assert_awaited_once()
    digests.create.assert_awaited_once()
    assert digest.has_data is True
    assert len(digest.articles) == 3
    assert len(digest.people_to_follow) == 2
    assert digest.action_item


@pytest.mark.asyncio
async def test_generate_digest_empty_without_context(
    service: NewsletterService, llm: MagicMock, sessions: MagicMock
) -> None:
    sessions.get = AsyncMock(return_value=None)
    digest = await service.generate_digest("u1")
    llm.complete_json.assert_not_awaited()
    assert digest.has_data is False


@pytest.mark.asyncio
async def test_generate_digest_fallback_on_bad_output(
    service: NewsletterService, llm: MagicMock, sessions: MagicMock
) -> None:
    sessions.get = AsyncMock(return_value=_session())
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    digest = await service.generate_digest("u1")
    assert digest.has_data is False
