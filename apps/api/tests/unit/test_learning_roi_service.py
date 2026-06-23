"""Unit tests for LearningRoiService (scoring engine isolated via monkeypatch)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.learning_roi.schemas import LearningItemCreate, LearningItemUpdate
from src.domains.learning_roi.service import LearningRoiService

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fake_engine(monkeypatch):
    # Deterministic, controllable score driven by cost so ranking is assertable.
    def fake_score_item(*, skills, cost, hours, item_type, signals):
        return SimpleNamespace(
            impact_score=int(cost), relevance=0.5, roi_score=int(cost),
            matched_skills=list(skills)[:1], rationale="because",
        )
    monkeypatch.setattr("src.domains.learning_roi.service.score_item", fake_score_item)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "i1", **doc})
    r.update = AsyncMock(return_value=None)
    r.get = AsyncMock(return_value=None)
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo: MagicMock) -> LearningRoiService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)  # → empty RoiSignals
    return LearningRoiService(repo, sessions)


async def test_create_returns_scored_item(service, repo) -> None:
    out = await service.create("u1", LearningItemCreate(title="SQL course", cost=100, skills=["sql"]))
    assert out.id == "i1"
    assert out.roi_score == 100
    assert out.rationale == "because"


async def test_list_ranked_sorts_by_roi_and_assigns_rank(service, repo) -> None:
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "a", "title": "cheap", "cost": 10},
        {"id": "b", "title": "pricey", "cost": 200},
        {"id": "c", "title": "mid", "cost": 50},
    ])
    items = await service.list_ranked("u1")
    assert [i.id for i in items] == ["b", "c", "a"]  # roi (=cost) descending
    assert [i.rank for i in items] == [1, 2, 3]


async def test_summary_empty(service, repo) -> None:
    s = await service.summary("u1")
    assert s.total_items == 0
    assert s.average_roi == 0


async def test_summary_rolls_up_totals(service, repo) -> None:
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "a", "title": "x", "cost": 100, "hours": 10},
        {"id": "b", "title": "y", "cost": 300, "hours": 20},
    ])
    s = await service.summary("u1")
    assert s.total_items == 2
    assert s.total_cost == 400.0
    assert s.total_hours == 30.0
    assert s.average_roi == 200  # (100+300)/2
    assert s.top_item_id == "b"


async def test_update_missing_raises_not_found(service, repo) -> None:
    with pytest.raises(NotFoundError):
        await service.update("u1", "missing", LearningItemUpdate(title="new"))


async def test_update_applies_patch(service, repo) -> None:
    repo.update = AsyncMock(return_value={"id": "i1", "title": "new", "cost": 5})
    out = await service.update("u1", "i1", LearningItemUpdate(title="new"))
    assert out.title == "new"


async def test_delete_missing_raises_not_found(service, repo) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
