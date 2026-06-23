"""Unit tests for FeedbackService."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut
from src.domains.feedback.service import FeedbackService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.list_for_user = AsyncMock(return_value=[])
    r.create = AsyncMock(
        return_value={"id": "f1", "category": "bug", "subject": "S", "message": "M", "created_at": NOW}
    )
    return r


@pytest.fixture
def service(repo: MagicMock) -> FeedbackService:
    return FeedbackService(repo)


async def test_create_returns_feedback_out(service: FeedbackService, repo: MagicMock) -> None:
    out = await service.create("u1", FeedbackCreate(subject="S", message="M", category="bug"))
    assert isinstance(out, FeedbackOut)
    assert out.id == "f1"
    repo.create.assert_awaited_once()
    uid, payload = repo.create.call_args.args
    assert uid == "u1"
    assert payload["category"] == "bug"


async def test_list_maps_docs(service: FeedbackService, repo: MagicMock) -> None:
    repo.list_for_user = AsyncMock(
        return_value=[
            {"id": "f1", "category": "idea", "subject": "A", "message": "m", "created_at": NOW},
            {"id": "f2", "category": "praise", "subject": "B", "message": "m", "created_at": NOW},
        ]
    )
    out = await service.list("u1")
    assert [f.id for f in out] == ["f1", "f2"]
    assert all(isinstance(f, FeedbackOut) for f in out)


async def test_list_passes_limit(service: FeedbackService, repo: MagicMock) -> None:
    await service.list("u1", limit=10)
    assert repo.list_for_user.call_args.kwargs["limit"] == 10
