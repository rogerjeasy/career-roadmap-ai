"""Unit tests for EvidenceService CRUD logic.

The Firestore repository is replaced by an AsyncMock — no Firestore, no network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.evidence.schemas import EvidenceCreate, EvidenceOut, EvidenceUpdate
from src.domains.evidence.service import EvidenceService


def _doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "e1",
        "title": "Shipped the billing service",
        "description": "Cut checkout latency 40%.",
        "type": "achievement",
        "link": "https://example.com",
        "date_label": "Mar 2026",
        "skills": ["python", "fastapi"],
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
def service(repo: MagicMock) -> EvidenceService:
    return EvidenceService(repo)


@pytest.mark.asyncio
async def test_list_maps_docs_to_schema(service: EvidenceService, repo: MagicMock) -> None:
    repo.list_for_user = AsyncMock(return_value=[_doc(), _doc(id="e2", title="Talk")])
    out = await service.list("u1")
    assert [e.id for e in out] == ["e1", "e2"]
    assert isinstance(out[0], EvidenceOut)
    assert out[0].skills == ["python", "fastapi"]
    repo.list_for_user.assert_awaited_once_with("u1", limit=100)


@pytest.mark.asyncio
async def test_create_passes_payload_and_returns_schema(
    service: EvidenceService, repo: MagicMock
) -> None:
    repo.create = AsyncMock(return_value=_doc(title="New cert", type="certification"))
    out = await service.create(
        "u1", EvidenceCreate(title="New cert", type="certification")
    )
    assert out.type == "certification"
    args, _ = repo.create.call_args
    assert args[0] == "u1"
    assert args[1]["title"] == "New cert"


@pytest.mark.asyncio
async def test_get_missing_raises_not_found(
    service: EvidenceService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")


@pytest.mark.asyncio
async def test_update_missing_raises_not_found(
    service: EvidenceService, repo: MagicMock
) -> None:
    repo.update = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.update("u1", "missing", EvidenceUpdate(title="x"))


@pytest.mark.asyncio
async def test_delete_missing_raises_not_found(
    service: EvidenceService, repo: MagicMock
) -> None:
    repo.hard_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


def test_from_doc_coerces_unknown_type() -> None:
    out = EvidenceOut.from_doc(_doc(type="not-a-real-type"))
    assert out.type == "other"


def test_update_patch_excludes_unset_fields() -> None:
    patch = EvidenceUpdate(title="Only title").to_patch()
    assert patch == {"title": "Only title"}
