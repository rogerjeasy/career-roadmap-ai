"""Unit tests for EvidenceService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.evidence.schemas import EvidenceCreate, EvidenceOut, EvidenceUpdate
from src.domains.evidence.service import EvidenceService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "e1", "created_at": NOW, **doc})
    r.update = AsyncMock(return_value=None)
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo) -> EvidenceService:
    return EvidenceService(repo)


async def test_create_returns_out(service) -> None:
    out = await service.create("u1", EvidenceCreate(title="Shipped X", type="project"))
    assert isinstance(out, EvidenceOut)
    assert out.type == "project"


async def test_get_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")


async def test_update_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.update("u1", "missing", EvidenceUpdate(title="new"))


async def test_update_applies_patch(service, repo) -> None:
    repo.update = AsyncMock(return_value={"id": "e1", "title": "new", "created_at": NOW})
    out = await service.update("u1", "e1", EvidenceUpdate(title="new"))
    assert out.title == "new"


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


async def test_list_maps_docs(service, repo) -> None:
    repo.list_for_user = AsyncMock(return_value=[{"id": "e1", "created_at": NOW}, {"id": "e2", "created_at": NOW}])
    out = await service.list("u1")
    assert [e.id for e in out] == ["e1", "e2"]
