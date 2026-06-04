"""Unit tests for ScheduleService weekly-budget logic.

Repositories are replaced by AsyncMock-backed mocks — no Firestore, no network.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.schedule.schemas import BudgetTargets, TimeLogCreate
from src.domains.schedule.service import ScheduleService


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _week_start_iso() -> str:
    today = _today().date()
    return (today - timedelta(days=today.weekday())).isoformat()


@pytest.fixture
def repos() -> dict[str, MagicMock]:
    def make() -> MagicMock:
        m = MagicMock()
        m.get = AsyncMock(return_value=None)
        m.list_for_user = AsyncMock(return_value=[])
        m.create = AsyncMock()
        m.update = AsyncMock()
        m.hard_delete = AsyncMock(return_value=True)
        return m

    return {"habits": make(), "blocks": make(), "time_logs": make(), "targets": make()}


@pytest.fixture
def service(repos: dict[str, MagicMock]) -> ScheduleService:
    return ScheduleService(repos["habits"], repos["blocks"], repos["time_logs"], repos["targets"])


@pytest.mark.asyncio
async def test_budget_sums_only_current_week_logs(
    service: ScheduleService, repos: dict[str, MagicMock]
) -> None:
    week_start = _week_start_iso()
    last_week = (_today().date() - timedelta(days=8)).isoformat()
    repos["targets"].get = AsyncMock(return_value={"build": 5, "read": 2})
    repos["time_logs"].list_for_user = AsyncMock(
        return_value=[
            {"category": "build", "hours": 2.0, "logged_on": week_start},
            {"category": "build", "hours": 1.5, "logged_on": week_start},
            {"category": "read", "hours": 3.0, "logged_on": last_week},  # excluded
            {"category": "network", "hours": 1.0, "logged_on": week_start},
        ]
    )

    budget = await service.get_budget("u1")
    by_id = {c.id: c for c in budget.categories}

    assert by_id["build"].hours_logged == 3.5
    assert by_id["build"].hours_target == 5
    assert by_id["read"].hours_logged == 0.0  # last week's log excluded
    assert by_id["read"].hours_target == 2
    assert by_id["network"].hours_logged == 1.0
    # Every category is always present with its display tone.
    assert {c.id for c in budget.categories} == {"build", "read", "network", "review"}
    assert by_id["build"].tone == "green"


@pytest.mark.asyncio
async def test_set_targets_creates_when_absent(
    service: ScheduleService, repos: dict[str, MagicMock]
) -> None:
    repos["targets"].get = AsyncMock(return_value=None)
    await service.set_budget_targets("u1", BudgetTargets(build=6, read=3, network=2, review=1))
    repos["targets"].create.assert_awaited_once()
    # Stored under a deterministic per-user doc id.
    _, kwargs = repos["targets"].create.call_args
    assert kwargs.get("doc_id") == "u1"


@pytest.mark.asyncio
async def test_log_time_defaults_to_today(
    service: ScheduleService, repos: dict[str, MagicMock]
) -> None:
    now = _today()
    repos["time_logs"].create = AsyncMock(
        return_value={
            "id": "t1",
            "category": "build",
            "hours": 2.0,
            "logged_on": now.date().isoformat(),
            "created_at": now,
        }
    )
    out = await service.log_time("u1", TimeLogCreate(category="build", hours=2.0))
    assert out.logged_on == now.date()
    args, _ = repos["time_logs"].create.call_args
    assert args[1]["logged_on"] == now.date().isoformat()
