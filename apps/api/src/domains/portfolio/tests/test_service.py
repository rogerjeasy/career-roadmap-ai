"""Unit tests for PortfolioService CRUD logic.

The Firestore repository is replaced by an AsyncMock — no Firestore, no network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.portfolio.schemas import (
    PortfolioItemCreate,
    PortfolioItemOut,
    PortfolioItemUpdate,
)
from src.domains.portfolio.service import PortfolioService


def _doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "title": "Roadmap AI",
        "description": "An agentic career coach.",
        "role": "Lead engineer",
        "url": "https://example.com",
        "repo_url": "https://github.com/example/repo",
        "status": "live",
        "date_label": "2026",
        "tech": ["python", "next.js"],
        "highlights": ["Shipped MVP in 6 weeks"],
        "created_at": datetime.now(timezone.utc),
    }
    base.update(over)
    return base


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.list_for_user = AsyncMock(return_value=[])
    m.get = AsyncMock(return_value=None)
    m.create = AsyncMock()
    m.update = AsyncMock()
    m.hard_delete = AsyncMock(return_value=True)
    return m


@pytest.fixture
def service(repo: MagicMock) -> PortfolioService:
    return PortfolioService(repo)


@pytest.mark.asyncio
async def test_list_maps_docs_to_schema(service: PortfolioService, repo: MagicMock) -> None:
    repo.list_for_user = AsyncMock(return_value=[_doc(), _doc(id="p2")])
    out = await service.list("u1")
    assert [p.id for p in out] == ["p1", "p2"]
    assert isinstance(out[0], PortfolioItemOut)
    assert out[0].tech == ["python", "next.js"]


@pytest.mark.asyncio
async def test_create_passes_payload_and_returns_schema(
    service: PortfolioService, repo: MagicMock
) -> None:
    repo.create = AsyncMock(return_value=_doc(title="Side project"))
    out = await service.create("u1", PortfolioItemCreate(title="Side project"))
    assert out.title == "Side project"
    args, _ = repo.create.call_args
    assert args[0] == "u1"
    assert args[1]["title"] == "Side project"


@pytest.mark.asyncio
async def test_get_missing_raises_not_found(
    service: PortfolioService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")


@pytest.mark.asyncio
async def test_update_missing_raises_not_found(
    service: PortfolioService, repo: MagicMock
) -> None:
    repo.update = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.update("u1", "missing", PortfolioItemUpdate(title="x"))


@pytest.mark.asyncio
async def test_delete_missing_raises_not_found(
    service: PortfolioService, repo: MagicMock
) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


def test_from_doc_coerces_unknown_status() -> None:
    out = PortfolioItemOut.from_doc(_doc(status="bogus"))
    assert out.status == "live"
