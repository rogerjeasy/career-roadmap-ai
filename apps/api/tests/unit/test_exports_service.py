"""Unit tests for ExportService (generators isolated via monkeypatch)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.exports.service import ExportService

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fake_generators(monkeypatch):
    monkeypatch.setattr("src.domains.exports.service.roadmap_to_markdown", lambda doc: "# Roadmap\n")
    monkeypatch.setattr("src.domains.exports.service.roadmap_to_ics", lambda doc: "BEGIN:VCALENDAR\n")


@pytest.fixture
def roadmaps() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=MagicMock())  # some roadmap doc
    return r


@pytest.fixture
def service(roadmaps) -> ExportService:
    return ExportService(roadmaps)


async def test_markdown_happy(service) -> None:
    assert await service.roadmap_markdown("u1", "r1") == "# Roadmap\n"


async def test_markdown_missing_raises(service, roadmaps) -> None:
    roadmaps.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.roadmap_markdown("u1", "missing")


async def test_ics_happy(service) -> None:
    result = await service.roadmap_ics("u1", "r1")
    assert result.startswith("BEGIN:VCALENDAR")


async def test_ics_missing_raises(service, roadmaps) -> None:
    roadmaps.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.roadmap_ics("u1", "missing")


async def test_reads_are_owner_scoped(service, roadmaps) -> None:
    await service.roadmap_markdown("u1", "r1")
    roadmaps.get.assert_awaited_with("r1", "u1")
