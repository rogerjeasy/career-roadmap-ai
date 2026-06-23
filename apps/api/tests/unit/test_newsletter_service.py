"""Unit tests for NewsletterService."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.newsletter.schemas import NewsletterDigest, NewsletterPrefsOut, NewsletterPrefsUpdate
from src.domains.newsletter.service import NewsletterService

pytestmark = pytest.mark.unit


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock(side_effect=lambda uid, data, doc_id=None: {"id": doc_id, **data})
    r.update = AsyncMock(side_effect=lambda uid, did, data: {"id": did, **data})
    return r


@pytest.fixture
def digests() -> MagicMock:
    d = MagicMock()
    d.get = AsyncMock(return_value=None)
    d.create = AsyncMock()
    d.update = AsyncMock()
    return d


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "period_label": "This week", "summary": "Big changes in PM hiring.",
        "articles": [{"title": "A", "why": "w"}], "people_to_follow": [{"name": "P"}],
        "action_item": "Apply to 3 roles", "confidence": 0.6,
    })
    return m


def _service(repo, digests, llm, session=None) -> NewsletterService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=session)
    return NewsletterService(repo, digests, llm, sessions)


async def test_get_prefs_defaults_when_absent(repo, digests, llm) -> None:
    out = await _service(repo, digests, llm).get("u1")
    assert isinstance(out, NewsletterPrefsOut)
    assert out.subscribed is False


async def test_update_creates_when_absent(repo, digests, llm) -> None:
    await _service(repo, digests, llm).update("u1", NewsletterPrefsUpdate(subscribed=True))
    repo.create.assert_awaited_once()


async def test_update_updates_when_present(repo, digests, llm) -> None:
    repo.get = AsyncMock(return_value={"id": "u1", "subscribed": False})
    await _service(repo, digests, llm).update("u1", NewsletterPrefsUpdate(subscribed=True))
    repo.update.assert_awaited_once()


async def test_get_digest_empty_when_absent(repo, digests, llm) -> None:
    out = await _service(repo, digests, llm).get_digest("u1")
    assert out.has_data is False


async def test_generate_digest_without_context_returns_empty(repo, digests, llm) -> None:
    out = await _service(repo, digests, llm, session=None).generate_digest("u1")
    assert out.has_data is False
    digests.create.assert_not_called()


async def test_generate_digest_happy(repo, digests, llm) -> None:
    session = SimpleNamespace(
        user_profile_context=SimpleNamespace(target_role="PM", location="NYC"),
        plan_context=None,
    )
    out = await _service(repo, digests, llm, session=session).generate_digest("u1")
    assert out.has_data is True
    assert out.summary.startswith("Big changes")
    digests.create.assert_awaited_once()
