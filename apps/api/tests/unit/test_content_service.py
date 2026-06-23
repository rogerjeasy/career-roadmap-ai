"""Unit tests for ContentService (generation + consent-gated publish)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.content.schemas import ContentDraftOut, ContentGenerateInput
from src.domains.content.service import ContentService

pytestmark = pytest.mark.unit


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "title": "My update", "content": "Shipped a feature today.", "hashtags": ["#Career", "Growth"], "based_on": "milestone",
    })
    return m


@pytest.fixture
def integrations() -> MagicMock:
    m = MagicMock()
    m.doc_id = MagicMock(return_value="u1:linkedin")
    m.get = AsyncMock(return_value=None)  # LinkedIn NOT connected by default
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "d1", **doc})
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.update = AsyncMock(side_effect=lambda did, uid, patch: {"id": did, "kind": "linkedin_post", "tone": "professional", "content": "c", **patch})
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, llm, integrations) -> ContentService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    roadmaps = MagicMock()
    roadmaps.list_for_user = AsyncMock(return_value=[])
    return ContentService(repo, llm, sessions, roadmaps, integrations)


async def test_generate_persists_draft(service) -> None:
    out = await service.generate("u1", ContentGenerateInput(kind="linkedin_post", milestone="Launched"))
    assert isinstance(out, ContentDraftOut)
    assert out.status == "draft"
    assert out.hashtags == ["Career", "Growth"]  # leading # stripped


async def test_generate_empty_content_raises(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value={"content": "   "})
    with pytest.raises(ValidationError):
        await service.generate("u1", ContentGenerateInput(milestone="x"))


async def test_publish_without_linkedin_raises(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "approved"})
    with pytest.raises(ValidationError, match="Connect LinkedIn"):
        await service.set_status("u1", "d1", "published")


async def test_publish_with_linkedin_sets_published_at(service, repo, integrations) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "approved"})
    integrations.get = AsyncMock(return_value={"access_token": "tok"})
    out = await service.set_status("u1", "d1", "published")
    assert out.status == "published"
    _did, _uid, patch = repo.update.call_args.args
    assert patch["published_at"] is not None


async def test_approve_needs_no_consent(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "d1", "status": "draft"})
    out = await service.set_status("u1", "d1", "approved")
    assert out.status == "approved"


async def test_set_status_missing_raises(service, repo) -> None:
    with pytest.raises(NotFoundError):
        await service.set_status("u1", "missing", "approved")


async def test_get_and_delete_missing_raise(service, repo) -> None:
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
