"""Schedule domain — service layer for habits and weekly time blocks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.schedule.firestore_repository import (
    FirestoreHabitRepository,
    FirestoreScheduleBlockRepository,
)
from src.domains.schedule.schemas import (
    HabitCreate,
    HabitOut,
    HabitUpdate,
    ScheduleBlockCreate,
    ScheduleBlockOut,
)

logger = get_logger(__name__)

# Keep at most this many days of per-habit completion history.
_HISTORY_DAYS = 120


def _is_today(value: datetime | None) -> bool:
    if value is None:
        return False
    return value.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def _completed_dates(doc: dict) -> set[str]:
    """Set of completed ISO dates for a habit, migrating legacy docs that only
    stored ``last_completed_at``."""
    raw = doc.get("completed_dates")
    if isinstance(raw, list) and raw:
        return {str(d) for d in raw}
    # Legacy fallback: seed from last_completed_at if it was today.
    if _is_today(doc.get("last_completed_at")):
        return {datetime.now(timezone.utc).date().isoformat()}
    return set()


def _streak(dates: set[str]) -> int:
    """Consecutive completed days ending today (or yesterday if today is blank)."""
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    if today.isoformat() in dates:
        cursor = today
    elif (today - timedelta(days=1)).isoformat() in dates:
        cursor = today - timedelta(days=1)
    else:
        return 0
    count = 0
    while cursor.isoformat() in dates:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _week_completions(dates: set[str]) -> list[bool]:
    """Completion flags for the current week, Monday … Sunday."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)).isoformat() in dates for i in range(7)]


def _habit_out(doc: dict) -> HabitOut:
    dates = _completed_dates(doc)
    ordered = sorted(dates)
    return HabitOut(
        id=doc["id"],
        label=doc.get("label", ""),
        cadence=doc.get("cadence", "Daily"),
        streak=_streak(dates),
        done_today=datetime.now(timezone.utc).date().isoformat() in dates,
        created_at=doc["created_at"],
        completed_dates=ordered[-_HISTORY_DAYS:],
        week_completions=_week_completions(dates),
    )


class ScheduleService:
    def __init__(
        self,
        habits: FirestoreHabitRepository,
        blocks: FirestoreScheduleBlockRepository,
    ) -> None:
        self._habits = habits
        self._blocks = blocks

    # ── Habits ────────────────────────────────────────────────────────────────

    async def list_habits(self, user_id: str) -> list[HabitOut]:
        docs = await self._habits.list_for_user(user_id, limit=100, order_desc=False)
        return [_habit_out(d) for d in docs]

    async def create_habit(self, user_id: str, payload: HabitCreate) -> HabitOut:
        doc = await self._habits.create(
            user_id,
            {
                "label": payload.label,
                "cadence": payload.cadence,
                "completed_dates": [],
                "last_completed_at": None,
            },
        )
        return _habit_out(doc)

    async def update_habit(self, user_id: str, habit_id: str, payload: HabitUpdate) -> HabitOut:
        doc = await self._habits.update(habit_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Habit '{habit_id}' not found")
        return _habit_out(doc)

    async def toggle_habit(self, user_id: str, habit_id: str) -> HabitOut:
        """Toggle today's completion in the habit's completion history."""
        current = await self._habits.get(habit_id, user_id)
        if current is None:
            raise NotFoundError(f"Habit '{habit_id}' not found")

        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        dates = _completed_dates(current)
        if today in dates:
            dates.discard(today)
            last_completed_at = None
        else:
            dates.add(today)
            last_completed_at = now

        patch = {
            "completed_dates": sorted(dates)[-_HISTORY_DAYS:],
            "last_completed_at": last_completed_at,
        }
        doc = await self._habits.update(habit_id, user_id, patch)
        assert doc is not None  # existence verified above
        return _habit_out(doc)

    async def delete_habit(self, user_id: str, habit_id: str) -> None:
        deleted = await self._habits.hard_delete(habit_id, user_id)
        if not deleted:
            raise NotFoundError(f"Habit '{habit_id}' not found")

    # ── Time blocks ───────────────────────────────────────────────────────────

    async def list_blocks(self, user_id: str) -> list[ScheduleBlockOut]:
        docs = await self._blocks.list_for_user(user_id, limit=200, order_desc=False)
        return [ScheduleBlockOut.from_doc(d) for d in docs]

    async def create_block(self, user_id: str, payload: ScheduleBlockCreate) -> ScheduleBlockOut:
        doc = await self._blocks.create(user_id, payload.model_dump())
        return ScheduleBlockOut.from_doc(doc)

    async def delete_block(self, user_id: str, block_id: str) -> None:
        deleted = await self._blocks.hard_delete(block_id, user_id)
        if not deleted:
            raise NotFoundError(f"Schedule block '{block_id}' not found")


async def get_schedule_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> ScheduleService:
    return ScheduleService(
        FirestoreHabitRepository(db),
        FirestoreScheduleBlockRepository(db),
    )
