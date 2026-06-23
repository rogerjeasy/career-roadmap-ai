"""Unit tests for StorytellingService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.storytelling.schemas import StoryDraftOut, StoryGenerateInput
from src.domains.storytelling.service import StorytellingService

pytestmark = pytest.mark.unit


@pytest.fixture
def evidence() -> MagicMock:
    e = MagicMock()
    e.get = AsyncMock(return_value={"title": "Shipped X", "type": "project", "description": "d", "skills": ["py"]})
    return e


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "title": "My bullets", "content": "• did things", "highlights": ["impact"], "tips": ["quantify"]
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "d1", **doc})
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, evidence, llm) -> StorytellingService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return StorytellingService(repo, evidence, llm, sessions)


async def test_generate_requires_evidence(service, evidence) -> None:
    evidence.get = AsyncMock(return_value=None)  # no item resolves
    with pytest.raises(ValidationError):
        await service.generate("u1", StoryGenerateInput(evidence_ids=["e1"]))


async def test_generate_with_no_ids_raises(service) -> None:
    with pytest.raises(ValidationError):
        await service.generate("u1", StoryGenerateInput(evidence_ids=[]))


async def test_generate_persists_draft_with_evidence_titles(service, repo) -> None:
    out = await service.generate("u1", StoryGenerateInput(format="resume_bullets", evidence_ids=["e1"]))
    assert isinstance(out, StoryDraftOut)
    assert out.evidence_titles == ["Shipped X"]
    assert out.title == "My bullets"


async def test_generate_dedupes_evidence_ids(service, evidence) -> None:
    await service.generate("u1", StoryGenerateInput(evidence_ids=["e1", "e1", "e1"]))
    assert evidence.get.await_count == 1  # deduped before fetching


async def test_get_draft_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.get_draft("u1", "missing")


async def test_delete_draft_missing_raises(service, repo) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete_draft("u1", "missing")
