"""Regression tests for the Snapshots domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.snapshots.schemas import SnapshotOut
from src.domains.snapshots.service import SnapshotService

pytestmark = pytest.mark.regression


async def test_restore_autosnapshots_current_state_before_overwriting() -> None:
    # REGRESSION: restore must be itself undoable — the current roadmap is
    # auto-snapshotted (auto=True) before restore_in_place overwrites it.
    roadmap_doc = MagicMock()
    roadmap_doc.summary = "current"
    roadmap_doc.phases = []
    roadmap_doc.model_dump.return_value = {"summary": "current", "phases": []}

    repo = MagicMock()
    repo.get = AsyncMock(return_value={"id": "s1", "roadmap_id": "rm1", "snapshot": {"summary": "old", "phases": []}})
    repo.create = AsyncMock(side_effect=lambda uid, doc: {"id": "auto1", **doc})
    repo.list_for_user = AsyncMock(return_value=[])

    roadmaps = MagicMock()
    roadmaps.get = AsyncMock(return_value=roadmap_doc)
    roadmaps.restore_in_place = AsyncMock()

    # RoadmapDocument.model_validate(raw) must succeed — stub it out so the test
    # focuses on the auto-snapshot ordering, not roadmap schema details.
    import src.domains.snapshots.service as mod
    orig = mod.RoadmapDocument
    mod.RoadmapDocument = MagicMock()
    try:
        service = SnapshotService(repo, roadmaps)
        await service.restore("u1", "s1")
    finally:
        mod.RoadmapDocument = orig

    # An auto snapshot was created before restore_in_place ran.
    assert repo.create.await_count == 1
    auto_payload = repo.create.call_args.args[1]
    assert auto_payload["auto"] is True
    roadmaps.restore_in_place.assert_awaited_once()


def test_from_doc_defaults() -> None:
    out = SnapshotOut.from_doc({"id": "s1"})
    assert out.roadmap_id == ""
    assert out.phase_count == 0
    assert out.auto is False
