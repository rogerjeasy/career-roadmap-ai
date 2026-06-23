"""Unit tests for MonthlyPlanService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.monthly_plan.schemas import MonthlyPlanOut, MonthlyPlanUpsert
from src.domains.monthly_plan.service import MonthlyPlanService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.doc_id = MagicMock(side_effect=lambda uid, mid: f"{uid}:{mid}")
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock(side_effect=lambda uid, data, doc_id=None: {"id": doc_id, "created_at": NOW, **data})
    r.update = AsyncMock(side_effect=lambda did, uid, data: {"id": did, "created_at": NOW, **data})
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo) -> MonthlyPlanService:
    return MonthlyPlanService(repo)


async def test_list_sorted_by_month_id_ascending(service, repo) -> None:
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "1", "month_id": "2026-07", "month": "Jul"},
        {"id": "2", "month_id": "2026-05", "month": "May"},
        {"id": "3", "month_id": "2026-06", "month": "Jun"},
    ])
    out = await service.list("u1")
    assert [p.month_id for p in out] == ["2026-05", "2026-06", "2026-07"]


async def test_get_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.get("u1", "2026-06")


async def test_upsert_creates_when_absent(service, repo) -> None:
    out = await service.upsert("u1", MonthlyPlanUpsert(month_id="2026-06", month="June 2026"))
    assert isinstance(out, MonthlyPlanOut)
    repo.create.assert_awaited_once()
    repo.update.assert_not_called()


async def test_upsert_updates_when_present(service, repo) -> None:
    repo.get = AsyncMock(return_value={"id": "u1:2026-06", "month_id": "2026-06", "created_at": NOW})
    await service.upsert("u1", MonthlyPlanUpsert(month_id="2026-06", month="June 2026", theme="Ship"))
    repo.update.assert_awaited_once()
    repo.create.assert_not_called()


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "2026-06")
