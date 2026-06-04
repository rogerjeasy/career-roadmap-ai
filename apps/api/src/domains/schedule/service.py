"""Schedule domain — service layer for habits and weekly time blocks."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.schedule.firestore_repository import (
    FirestoreBudgetTargetRepository,
    FirestoreHabitRepository,
    FirestoreScheduleBlockRepository,
    FirestoreTimeLogRepository,
)
from src.domains.schedule.schemas import (
    CATEGORY_META,
    BlockCategory,
    BudgetCategoryOut,
    BudgetOut,
    BudgetTargets,
    HabitCreate,
    HabitOut,
    HabitUpdate,
    ScheduleBlockCreate,
    ScheduleBlockOut,
    TimeLogCreate,
    TimeLogOut,
)

logger = get_logger(__name__)

# Keep at most this many days of per-habit completion history.
_HISTORY_DAYS = 120

_CATEGORIES: list[BlockCategory] = ["build", "read", "network", "review"]


def _current_week_start() -> date:
    """Monday of the current UTC week."""
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=today.weekday())


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
        time_logs: FirestoreTimeLogRepository,
        budget_targets: FirestoreBudgetTargetRepository,
    ) -> None:
        self._habits = habits
        self._blocks = blocks
        self._time_logs = time_logs
        self._targets = budget_targets

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

    # ── Weekly time budget ──────────────────────────────────────────────────--

    async def get_budget(self, user_id: str) -> BudgetOut:
        """Weekly budget: target hours per category vs. hours logged this week."""
        targets_doc = await self._targets.get(user_id, user_id) or {}
        targets = {c: float(targets_doc.get(c, 0) or 0) for c in _CATEGORIES}

        week_start = _current_week_start()
        start_iso = week_start.isoformat()
        end_iso = (week_start + timedelta(days=6)).isoformat()

        logged = {c: 0.0 for c in _CATEGORIES}
        for log in await self._time_logs.list_for_user(user_id, limit=1000):
            category = log.get("category")
            if category not in logged:
                continue
            logged_on = str(log.get("logged_on", ""))
            if start_iso <= logged_on <= end_iso:
                logged[category] += float(log.get("hours", 0) or 0)

        categories: list[BudgetCategoryOut] = []
        for category in _CATEGORIES:
            label, tone = CATEGORY_META[category]
            categories.append(
                BudgetCategoryOut(
                    id=category,
                    label=label,
                    hours_logged=round(logged[category], 2),
                    hours_target=targets[category],
                    tone=tone,
                )
            )
        return BudgetOut(week_start=week_start, categories=categories)

    async def set_budget_targets(self, user_id: str, payload: BudgetTargets) -> BudgetOut:
        data = payload.model_dump()
        existing = await self._targets.get(user_id, user_id)
        if existing is None:
            await self._targets.create(user_id, data, doc_id=user_id)
        else:
            await self._targets.update(user_id, user_id, data)
        return await self.get_budget(user_id)

    async def log_time(self, user_id: str, payload: TimeLogCreate) -> TimeLogOut:
        logged_on = (payload.logged_on or datetime.now(timezone.utc).date()).isoformat()
        doc = await self._time_logs.create(
            user_id,
            {"category": payload.category, "hours": payload.hours, "logged_on": logged_on},
        )
        return TimeLogOut.from_doc(doc)

    async def list_time_logs(self, user_id: str) -> list[TimeLogOut]:
        """Time-log entries for the current week, newest-first."""
        week_start = _current_week_start()
        start_iso = week_start.isoformat()
        end_iso = (week_start + timedelta(days=6)).isoformat()
        out: list[TimeLogOut] = []
        for log in await self._time_logs.list_for_user(user_id, limit=1000):
            logged_on = str(log.get("logged_on", ""))
            if start_iso <= logged_on <= end_iso:
                out.append(TimeLogOut.from_doc(log))
        return out

    async def delete_time_log(self, user_id: str, log_id: str) -> None:
        deleted = await self._time_logs.hard_delete(log_id, user_id)
        if not deleted:
            raise NotFoundError(f"Time log '{log_id}' not found")


async def get_schedule_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> ScheduleService:
    return ScheduleService(
        FirestoreHabitRepository(db),
        FirestoreScheduleBlockRepository(db),
        FirestoreTimeLogRepository(db),
        FirestoreBudgetTargetRepository(db),
    )
