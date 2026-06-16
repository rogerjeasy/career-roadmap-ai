"""Unit tests for RoadmapService.

The repository is replaced by a plain MagicMock with AsyncMock methods —
no Firestore setup, no Firebase credentials, no network.  This is exactly
what the Protocol-based interface enables.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.exceptions import NotFoundError
from src.domains.roadmap.schemas import RoadmapDocument, RoadmapSummary
from src.domains.roadmap.service import RoadmapService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_doc(roadmap_id: str = "r1", user_id: str = "u1") -> RoadmapDocument:
    return RoadmapDocument(
        id=roadmap_id,
        user_id=user_id,
        session_id="session-1",
        request_id="request-1",
        summary="Become a senior ML engineer in 12 months.",
        confidence=0.88,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def _make_summary(roadmap_id: str = "r1", user_id: str = "u1") -> RoadmapSummary:
    return RoadmapSummary(
        id=roadmap_id,
        user_id=user_id,
        session_id="session-1",
        request_id="request-1",
        summary="Become a senior ML engineer in 12 months.",
        confidence=0.88,
        status="completed",
        phase_count=3,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def repo() -> MagicMock:
    """In-memory mock repository — satisfies IRoadmapRepository structurally."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.list_for_user = AsyncMock(return_value=[])
    mock.save = AsyncMock(return_value="r1")
    mock.soft_delete = AsyncMock()
    return mock


@pytest.fixture
def service(repo: MagicMock) -> RoadmapService:
    return RoadmapService(repo)


# ── get ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_none_when_repo_returns_none(service: RoadmapService, repo: MagicMock) -> None:
    result = await service.get("missing", "u1")
    assert result is None
    repo.get.assert_awaited_once_with("missing", "u1")


@pytest.mark.asyncio
async def test_get_returns_document_from_repo(service: RoadmapService, repo: MagicMock) -> None:
    doc = _make_doc()
    repo.get.return_value = doc

    result = await service.get("r1", "u1")

    assert result is doc
    repo.get.assert_awaited_once_with("r1", "u1")


# ── list_for_user ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_returns_empty_when_repo_empty(service: RoadmapService) -> None:
    result = await service.list_for_user("u1")
    assert result == []


@pytest.mark.asyncio
async def test_list_passes_limit_to_repo(service: RoadmapService, repo: MagicMock) -> None:
    repo.list_for_user.return_value = [_make_summary()]

    result = await service.list_for_user("u1", limit=5)

    assert len(result) == 1
    repo.list_for_user.assert_awaited_once_with("u1", limit=5)


# ── delete ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_raises_not_found_when_missing(service: RoadmapService, repo: MagicMock) -> None:
    repo.get.return_value = None

    with pytest.raises(NotFoundError):
        await service.delete("missing", "u1")

    repo.soft_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_calls_soft_delete_on_existing(service: RoadmapService, repo: MagicMock) -> None:
    repo.get.return_value = _make_doc()

    await service.delete("r1", "u1")

    repo.soft_delete.assert_awaited_once_with("r1", "u1")


@pytest.mark.asyncio
async def test_delete_checks_ownership_via_get(service: RoadmapService, repo: MagicMock) -> None:
    """get() enforces row-level isolation; delete() honours whatever get() returns."""
    repo.get.return_value = None  # repo returns None for wrong owner

    with pytest.raises(NotFoundError):
        await service.delete("r1", "wrong-user")

    repo.soft_delete.assert_not_awaited()


# ── milestone progress ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_progress_passes_through_repo(service: RoadmapService, repo: MagicMock) -> None:
    updated = datetime.now(timezone.utc)
    repo.get_progress = AsyncMock(return_value=(["p1:0", "p2:3"], updated))

    completed, ts = await service.get_progress("r1", "u1")

    assert completed == ["p1:0", "p2:3"]
    assert ts == updated
    repo.get_progress.assert_awaited_once_with("r1", "u1")


@pytest.mark.asyncio
async def test_toggle_milestone_adds_when_absent(service: RoadmapService, repo: MagicMock) -> None:
    repo.get_progress = AsyncMock(return_value=(["p1:0"], None))
    repo.set_progress = AsyncMock(return_value=datetime.now(timezone.utc))

    completed, _ = await service.toggle_milestone("r1", "u1", "p1:1")

    assert completed == ["p1:0", "p1:1"]  # sorted, new key added
    repo.set_progress.assert_awaited_once_with("r1", "u1", ["p1:0", "p1:1"])


@pytest.mark.asyncio
async def test_toggle_milestone_removes_when_present(service: RoadmapService, repo: MagicMock) -> None:
    repo.get_progress = AsyncMock(return_value=(["p1:0", "p1:1"], None))
    repo.set_progress = AsyncMock(return_value=datetime.now(timezone.utc))

    completed, _ = await service.toggle_milestone("r1", "u1", "p1:0")

    assert completed == ["p1:1"]  # toggled off
    repo.set_progress.assert_awaited_once_with("r1", "u1", ["p1:1"])


# ── phase editing ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_phase_raises_not_found_when_missing(
    service: RoadmapService, repo: MagicMock
) -> None:
    repo.update_phase = AsyncMock(return_value=False)

    with pytest.raises(NotFoundError):
        await service.update_phase("r1", "u1", "missing", {"title": "X"})


@pytest.mark.asyncio
async def test_update_phase_cleans_milestones_and_returns_doc(
    service: RoadmapService, repo: MagicMock
) -> None:
    repo.update_phase = AsyncMock(return_value=True)
    repo.get_progress = AsyncMock(return_value=([], None))
    repo.set_progress = AsyncMock()
    repo.get = AsyncMock(return_value=_make_doc())

    doc = await service.update_phase(
        "r1", "u1", "p1", {"milestones": ["  ship it  ", "", "  "]}
    )

    # whitespace trimmed, empties dropped
    repo.update_phase.assert_awaited_once_with("r1", "u1", "p1", {"milestones": ["ship it"]})
    assert doc.id == "r1"


@pytest.mark.asyncio
async def test_update_phase_prunes_out_of_range_progress(
    service: RoadmapService, repo: MagicMock
) -> None:
    repo.update_phase = AsyncMock(return_value=True)
    repo.get = AsyncMock(return_value=_make_doc())
    # phase shrinks to 2 milestones — p1:2 must be dropped, p2:0 untouched
    repo.get_progress = AsyncMock(return_value=(["p1:0", "p1:2", "p2:0"], None))
    repo.set_progress = AsyncMock()

    await service.update_phase("r1", "u1", "p1", {"milestones": ["a", "b"]})

    repo.set_progress.assert_awaited_once_with("r1", "u1", ["p1:0", "p2:0"])


@pytest.mark.asyncio
async def test_delete_phase_discards_its_progress(
    service: RoadmapService, repo: MagicMock
) -> None:
    repo.delete_phase = AsyncMock(return_value=True)
    repo.get = AsyncMock(return_value=_make_doc())
    repo.get_progress = AsyncMock(return_value=(["p1:0", "p2:0", "p2:1"], None))
    repo.set_progress = AsyncMock()

    await service.delete_phase("r1", "u1", "p2")

    repo.set_progress.assert_awaited_once_with("r1", "u1", ["p1:0"])


@pytest.mark.asyncio
async def test_add_phase_raises_when_roadmap_missing(
    service: RoadmapService, repo: MagicMock
) -> None:
    repo.add_phase = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await service.add_phase("r1", "u1", {"title": "New phase"})


@pytest.mark.asyncio
async def test_reorder_phases_returns_doc(service: RoadmapService, repo: MagicMock) -> None:
    repo.reorder_phases = AsyncMock(return_value=True)
    repo.get = AsyncMock(return_value=_make_doc())

    doc = await service.reorder_phases("r1", "u1", ["p2", "p1"])

    repo.reorder_phases.assert_awaited_once_with("r1", "u1", ["p2", "p1"])
    assert doc.id == "r1"
