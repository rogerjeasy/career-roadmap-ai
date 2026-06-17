"""Unit tests for FeedbackService.

The Firestore repository is replaced by an AsyncMock — no Firestore, no network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut
from src.domains.feedback.service import FeedbackService


def _doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "f1",
        "category": "idea",
        "subject": "Dark mode",
        "message": "Please add a dark theme.",
        "rating": None,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(over)
    return base


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.list_for_user = AsyncMock(return_value=[])
    m.create = AsyncMock()
    return m


@pytest.fixture
def service(repo: MagicMock) -> FeedbackService:
    return FeedbackService(repo)


@pytest.mark.asyncio
async def test_list_is_user_scoped_and_mapped(
    service: FeedbackService, repo: MagicMock
) -> None:
    repo.list_for_user = AsyncMock(return_value=[_doc(), _doc(id="f2", category="bug")])
    out = await service.list("u1")
    assert [f.id for f in out] == ["f1", "f2"]
    assert isinstance(out[0], FeedbackOut)
    repo.list_for_user.assert_awaited_once_with("u1", limit=50)


@pytest.mark.asyncio
async def test_create_passes_payload_and_returns_schema(
    service: FeedbackService, repo: MagicMock
) -> None:
    repo.create = AsyncMock(
        return_value=_doc(category="bug", subject="Crash", message="It crashed")
    )
    out = await service.create(
        "u1", FeedbackCreate(category="bug", subject="Crash", message="It crashed")
    )
    assert out.category == "bug"
    args, _ = repo.create.call_args
    assert args[0] == "u1"
    assert args[1]["subject"] == "Crash"


@pytest.mark.asyncio
async def test_service_is_append_only(service: FeedbackService) -> None:
    # Feedback is an immutable audit trail — no update/delete surface.
    assert not hasattr(service, "update")
    assert not hasattr(service, "delete")


def test_from_doc_coerces_unknown_category() -> None:
    out = FeedbackOut.from_doc(_doc(category="spam"))
    assert out.category == "other"
