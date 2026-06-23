"""Unit tests for DiscoveryService."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.discovery.schemas import DiscoveryResult
from src.domains.discovery.service import DiscoveryService

pytestmark = pytest.mark.unit


def _session_with_profile(**over):
    profile = SimpleNamespace(current_role="Engineer", location="NYC", skills=["python"], additional={})
    for k, v in over.items():
        setattr(profile, k, v)
    return SimpleNamespace(user_profile_context=profile)


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "based_on": "your CV", "confidence": 0.7,
        "paths": [{"title": "Data Scientist", "fit_score": 80}],
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock()
    r.update = AsyncMock()
    return r


def _service(repo, llm, session) -> DiscoveryService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=session)
    return DiscoveryService(repo, llm, sessions)


async def test_get_returns_empty_when_no_doc(repo, llm) -> None:
    out = await _service(repo, llm, None).get("u1")
    assert isinstance(out, DiscoveryResult)
    assert out.has_data is False


async def test_get_returns_cached(repo, llm) -> None:
    repo.get = AsyncMock(return_value={"paths": [{"title": "X"}], "based_on": "cv"})
    out = await _service(repo, llm, None).get("u1")
    assert out.has_data is True
    assert out.paths[0].title == "X"


async def test_generate_without_context_returns_no_data(repo, llm) -> None:
    out = await _service(repo, llm, None).generate("u1")  # session None → no context
    assert out.has_data is False
    repo.create.assert_not_called()


async def test_generate_happy_persists_and_returns_paths(repo, llm) -> None:
    out = await _service(repo, llm, _session_with_profile()).generate("u1")
    assert out.has_data is True
    assert out.paths[0].title == "Data Scientist"
    repo.create.assert_awaited_once()


async def test_generate_updates_existing(repo, llm) -> None:
    repo.get = AsyncMock(return_value={"paths": []})  # existing doc
    await _service(repo, llm, _session_with_profile()).generate("u1")
    repo.update.assert_awaited_once()
    repo.create.assert_not_called()


async def test_generate_llm_error_returns_empty(repo, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    out = await _service(repo, llm, _session_with_profile()).generate("u1")
    assert out.has_data is False
