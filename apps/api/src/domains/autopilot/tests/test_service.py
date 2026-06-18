"""Unit tests for the autopilot service (signal assembly, dedupe, status)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.domains.autopilot.service import AutopilotService
from src.session.models import PlanContext, SessionData, UserProfileContext


def _session(*, roadmap: bool, skills=None, trending=None) -> SessionData:
    now = datetime.now(timezone.utc)
    snapshot = {}
    if trending is not None:
        snapshot = {"market": {"trending_skills": [{"name": t} for t in trending]}}
    return SessionData(
        user_id="u1",
        email="u@example.com",
        created_at=now,
        last_active_at=now,
        user_profile_context=UserProfileContext(skills=skills or []),
        plan_context=PlanContext(roadmap_id="r1" if roadmap else None, snapshot=snapshot),
    )


def _proposals_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.list_for_user.return_value = []
    repo.create.side_effect = lambda user_id, data, doc_id=None: {"id": "p", **data}
    repo.update.side_effect = lambda doc_id, user_id, patch: {"id": doc_id, **patch}
    return repo


@pytest.mark.asyncio
async def test_refresh_creates_market_drift_proposal() -> None:
    repo = _proposals_repo()
    reviews = AsyncMock()
    reviews.list_for_user.return_value = [
        {"created_at": datetime.now(timezone.utc) - timedelta(days=1)}
    ]
    habits = AsyncMock()
    habits.list_for_user.return_value = []
    sessions = AsyncMock()
    sessions.get.return_value = _session(roadmap=True, skills=["Python"], trending=["RAG", "Python"])

    svc = AutopilotService(repo, reviews, habits, sessions)
    # list_open reads back created docs; emulate by returning the created proposal.
    created: list[dict] = []
    repo.create.side_effect = lambda user_id, data, doc_id=None: created.append({"id": str(len(created)), **data}) or created[-1]
    repo.list_for_user.side_effect = [[], created]

    result = await svc.refresh("u1")

    assert any(p.kind == "market_drift" for p in result)
    # "Python" is already held, so only "RAG" should surface.
    drift = next(p for p in result if p.kind == "market_drift")
    assert "RAG" in drift.detail and "Python" not in drift.detail


@pytest.mark.asyncio
async def test_refresh_dedupes_open_proposals() -> None:
    repo = _proposals_repo()
    # An open kickstart already exists → refresh must not create a duplicate.
    repo.list_for_user.return_value = [
        {"id": "x", "status": "open", "signature": "kickstart", "kind": "kickstart",
         "title": "t", "detail": "d", "severity": "info", "action_label": "a", "action_route": "/onboarding"}
    ]
    reviews = AsyncMock()
    reviews.list_for_user.return_value = []
    habits = AsyncMock()
    habits.list_for_user.return_value = []
    sessions = AsyncMock()
    sessions.get.return_value = _session(roadmap=False)

    svc = AutopilotService(repo, reviews, habits, sessions)
    await svc.refresh("u1")

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_habits_detected_from_week_completions() -> None:
    repo = _proposals_repo()
    reviews = AsyncMock()
    reviews.list_for_user.return_value = [{"created_at": datetime.now(timezone.utc)}]
    habits = AsyncMock()
    habits.list_for_user.return_value = [
        {"name": "Deep work", "week_completions": [True, False, False, False, False, False, False]},
        {"name": "Reading", "week_completions": [True, True, True, False, False, False, False]},
    ]
    sessions = AsyncMock()
    sessions.get.return_value = _session(roadmap=True)

    svc = AutopilotService(repo, reviews, habits, sessions)
    signals = await svc._assemble_signals("u1")

    assert signals.low_habits == ["Deep work"]  # 1 completion < 2; Reading has 3


@pytest.mark.asyncio
async def test_set_status_updates_proposal() -> None:
    repo = _proposals_repo()
    svc = AutopilotService(repo, AsyncMock(), AsyncMock(), AsyncMock())

    out = await svc.set_status("u1", "p1", "dismissed")
    assert out is not None
    assert out.status == "dismissed"
    repo.update.assert_awaited_once()
