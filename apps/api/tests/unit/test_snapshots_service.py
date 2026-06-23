"""Unit tests for SnapshotService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.snapshots.service import SnapshotService

pytestmark = pytest.mark.unit


def _roadmap_doc() -> MagicMock:
    doc = MagicMock()
    doc.summary = "A roadmap"
    doc.phases = [1, 2, 3]
    doc.model_dump.return_value = {"summary": "A roadmap", "phases": []}
    return doc


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "s1", **doc})
    r.get = AsyncMock(return_value=None)
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def roadmaps() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=_roadmap_doc())
    r.restore_in_place = AsyncMock()
    return r


@pytest.fixture
def service(repo: MagicMock, roadmaps: MagicMock) -> SnapshotService:
    return SnapshotService(repo, roadmaps)


async def test_create_captures_roadmap(service, repo, roadmaps) -> None:
    out = await service.create("u1", "rm1", "My label")
    assert out.id == "s1"
    _uid, payload = repo.create.call_args.args
    assert payload["roadmap_id"] == "rm1"
    assert payload["phase_count"] == 3
    assert payload["label"] == "My label"


async def test_create_missing_roadmap_raises(service, roadmaps) -> None:
    roadmaps.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.create("u1", "rm1", "x")


async def test_create_auto_label_default(service, repo) -> None:
    await service.create("u1", "rm1", "", auto=True)
    _uid, payload = repo.create.call_args.args
    assert payload["auto"] is True
    assert "Auto-saved" in payload["label"]


async def test_list_filters_by_roadmap_id(service, repo) -> None:
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "s1", "roadmap_id": "rm1", "summary": "", "phase_count": 1, "auto": False},
        {"id": "s2", "roadmap_id": "rm2", "summary": "", "phase_count": 1, "auto": False},
    ])
    out = await service.list("u1", "rm1")
    assert [s.id for s in out] == ["s1"]


async def test_restore_missing_snapshot_raises(service, repo) -> None:
    repo.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.restore("u1", "missing")


async def test_restore_when_roadmap_gone_raises(service, repo, roadmaps) -> None:
    repo.get = AsyncMock(return_value={"id": "s1", "roadmap_id": "rm1", "snapshot": {}})
    roadmaps.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.restore("u1", "s1")


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
