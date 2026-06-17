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
def service(repo: MagicMock) -> NewsletterService:
    return NewsletterService(repo)


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
