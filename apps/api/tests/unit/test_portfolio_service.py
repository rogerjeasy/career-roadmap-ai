"""Unit tests for PortfolioService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.portfolio.schemas import PortfolioItemCreate, PortfolioItemOut, PortfolioItemUpdate
from src.domains.portfolio.service import PortfolioService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "p1", "created_at": NOW, **doc})
    r.update = AsyncMock(return_value=None)
    r.hard_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo) -> PortfolioService:
    return PortfolioService(repo)


async def test_create_returns_out(service) -> None:
    out = await service.create("u1", PortfolioItemCreate(title="My app", status="live"))
    assert isinstance(out, PortfolioItemOut)
    assert out.status == "live"


async def test_get_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")


async def test_update_missing_raises(service) -> None:
    with pytest.raises(NotFoundError):
        await service.update("u1", "missing", PortfolioItemUpdate(title="x"))


async def test_update_applies_patch(service, repo) -> None:
    repo.update = AsyncMock(return_value={"id": "p1", "title": "new", "created_at": NOW})
    out = await service.update("u1", "p1", PortfolioItemUpdate(title="new"))
    assert out.title == "new"


async def test_delete_missing_raises(service, repo) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")
