"""Unit tests for WellnessService."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.wellness.schemas import WellnessCheckinCreate, WellnessCheckinOut, WellnessStatus
from src.domains.wellness.service import WellnessService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(
        return_value={"id": "w1", "energy": 4, "stress": 2, "motivation": 5, "created_at": NOW}
    )
    r.list_for_user = AsyncMock(return_value=[])
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo: MagicMock) -> WellnessService:
    return WellnessService(repo)


async def test_log_checkin_returns_out(service: WellnessService) -> None:
    out = await service.log_checkin(
        "u1", WellnessCheckinCreate(energy=4, stress=2, motivation=5)
    )
    assert isinstance(out, WellnessCheckinOut)
    assert out.id == "w1"


async def test_delete_checkin_ok(service: WellnessService, repo: MagicMock) -> None:
    await service.delete_checkin("u1", "w1")
    repo.soft_delete.assert_awaited_once_with("w1", "u1")


async def test_delete_missing_checkin_raises_not_found(service: WellnessService, repo: MagicMock) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete_checkin("u1", "missing")


async def test_status_maps_engine_result(service: WellnessService, repo: MagicMock, monkeypatch) -> None:
    repo.list_for_user = AsyncMock(
        return_value=[{"energy": 2, "stress": 5, "motivation": 2, "hours_worked": 60, "sleep_hours": 5}]
    )
    fake = SimpleNamespace(
        risk_score=72,
        risk_level="high",
        trend="worsening",
        drivers=["low sleep"],
        recommendation="Take a break",
        recovery_suggested=True,
        sample_size=1,
    )
    monkeypatch.setattr("src.domains.wellness.service.assess", lambda signals: fake)

    status = await service.status("u1")
    assert isinstance(status, WellnessStatus)
    assert status.risk_score == 72
    assert status.risk_level == "high"
    assert status.recovery_suggested is True
