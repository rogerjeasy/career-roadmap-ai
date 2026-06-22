"""Unit tests for the Applications domain.

Covers the two areas with non-trivial logic added for the pipeline:
  • the legacy → canonical status mapping (``normalize_status`` / ``from_doc``);
  • the status timeline appended on every stage change;
  • the scheduled reminder sweep (``fire_due_reminders``).

The Firestore repository and PushService are replaced by mocks — no Firestore,
no network.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.applications.schemas import (
    ApplicationOut,
    ApplicationUpdate,
    normalize_status,
)
from src.domains.applications.service import ApplicationService, fire_due_reminders

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


# ── Legacy / canonical status mapping ───────────────────────────────────────


@pytest.mark.parametrize(
    ("raw_status", "raw_outcome", "expected"),
    [
        ("interviewing", None, ("interview", None)),
        ("accepted", None, ("closed", "accepted")),
        ("rejected", None, ("closed", "rejected")),
        ("withdrawn", None, ("closed", "withdrawn")),
        ("saved", None, ("saved", None)),
        ("screening", None, ("screening", None)),  # current value passes through
        ("nonsense", None, ("saved", None)),  # unknown falls back to saved
        ("closed", "accepted", ("closed", "accepted")),  # explicit outcome kept
        ("interviewing", "rejected", ("interview", "rejected")),  # explicit wins
    ],
)
def test_normalize_status(
    raw_status: str, raw_outcome: str | None, expected: tuple[str, str | None]
) -> None:
    assert normalize_status(raw_status, raw_outcome) == expected


def test_from_doc_maps_legacy_accepted_to_closed_with_outcome() -> None:
    out = ApplicationOut.from_doc(
        {"id": "a1", "company": "Acme", "role": "PM", "status": "accepted"}
    )
    assert out.status == "closed"
    assert out.outcome == "accepted"


def test_from_doc_sorts_reminders_and_reads_stage_notes() -> None:
    out = ApplicationOut.from_doc(
        {
            "id": "a1",
            "status": "interview",
            "stage_notes": {"interview": "Met the team"},
            "reminders": [
                {"id": "r2", "title": "Later", "due_at": NOW + timedelta(days=2)},
                {"id": "r1", "title": "Sooner", "due_at": NOW},
                {"id": "bad", "title": "No due date"},  # dropped — no due_at
            ],
        }
    )
    assert out.stage_notes == {"interview": "Met the team"}
    assert [r.id for r in out.reminders] == ["r1", "r2"]


# ── Timeline on status change ───────────────────────────────────────────────


def _doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "a1",
        "user_id": "u1",
        "company": "Acme",
        "role": "PM",
        "status": "applied",
        "applied_at": NOW - timedelta(days=3),
        "timeline": [{"status": "applied", "outcome": None, "note": "", "at": NOW}],
    }
    base.update(over)
    return base


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=_doc())
    m.update = AsyncMock(side_effect=lambda _id, _uid, patch: {**_doc(), **patch})
    return m


@pytest.fixture
def service(repo: MagicMock) -> ApplicationService:
    return ApplicationService(repo, MagicMock(), MagicMock(), MagicMock())


@pytest.mark.asyncio
async def test_update_appends_timeline_event_on_status_change(
    service: ApplicationService, repo: MagicMock
) -> None:
    await service.update("u1", "a1", ApplicationUpdate(status="interview"))
    _id, _uid, patch = repo.update.call_args.args
    assert len(patch["timeline"]) == 2
    assert patch["timeline"][-1]["status"] == "interview"
    assert patch["outcome"] is None  # cleared when not closed


@pytest.mark.asyncio
async def test_update_to_closed_records_outcome(
    service: ApplicationService, repo: MagicMock
) -> None:
    repo.get = AsyncMock(return_value=_doc(status="offer"))
    await service.update("u1", "a1", ApplicationUpdate(status="closed", outcome="accepted"))
    _id, _uid, patch = repo.update.call_args.args
    assert patch["timeline"][-1] == {
        "status": "closed",
        "outcome": "accepted",
        "note": "",
        "at": patch["timeline"][-1]["at"],
    }
    assert patch["outcome"] == "accepted"


@pytest.mark.asyncio
async def test_update_without_status_change_does_not_touch_timeline(
    service: ApplicationService, repo: MagicMock
) -> None:
    await service.update("u1", "a1", ApplicationUpdate(notes="call back Friday"))
    _id, _uid, patch = repo.update.call_args.args
    assert "timeline" not in patch
    assert patch == {"notes": "call back Friday"}


# ── Reminder sweep ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_due_reminders_sends_once_and_stamps_fired_at() -> None:
    reminders = [
        {"id": "r1", "title": "Follow up", "due_at": NOW - timedelta(hours=1), "done": False},
        {"id": "r2", "title": "Future", "due_at": NOW + timedelta(days=1), "done": False},
        {"id": "r3", "title": "Done", "due_at": NOW - timedelta(days=2), "done": True},
        {
            "id": "r4",
            "title": "Already sent",
            "due_at": NOW - timedelta(days=1),
            "done": False,
            "fired_at": NOW - timedelta(days=1),
        },
    ]
    repo = MagicMock()
    repo.iter_all = AsyncMock(
        return_value=[{"id": "a1", "user_id": "u1", "role": "PM", "company": "Acme", "reminders": reminders}]
    )
    repo.update = AsyncMock()
    push = MagicMock()
    push.send_to_user = AsyncMock()

    fired = await fire_due_reminders(repo, push, now=NOW)

    assert fired == 1
    push.send_to_user.assert_awaited_once()
    kwargs = push.send_to_user.await_args.kwargs
    assert "Follow up" in kwargs["body"]
    assert "PM at Acme" in kwargs["body"]
    assert kwargs["url"] == "/applications"
    # Only the genuinely-due, unsent reminder is stamped.
    assert reminders[0]["fired_at"] == NOW
    assert "fired_at" not in reminders[1]
    repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_fire_due_reminders_noop_when_nothing_due() -> None:
    repo = MagicMock()
    repo.iter_all = AsyncMock(
        return_value=[
            {
                "id": "a1",
                "user_id": "u1",
                "role": "PM",
                "company": "Acme",
                "reminders": [
                    {"id": "r2", "title": "Future", "due_at": NOW + timedelta(days=1), "done": False}
                ],
            }
        ]
    )
    repo.update = AsyncMock()
    push = MagicMock()
    push.send_to_user = AsyncMock()

    fired = await fire_due_reminders(repo, push, now=NOW)

    assert fired == 0
    push.send_to_user.assert_not_awaited()
    repo.update.assert_not_awaited()
