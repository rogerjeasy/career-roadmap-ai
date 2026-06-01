"""Schedule domain — service layer for habits and weekly time blocks."""
from __future__ import annotations

from datetime import datetime, timezone

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


def _is_today(value: datetime | None) -> bool:
    if value is None:
        return False
    return value.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def _habit_out(doc: dict) -> HabitOut:
    return HabitOut(
        id=doc["id"],
        label=doc.get("label", ""),
        cadence=doc.get("cadence", "Daily"),
        streak=int(doc.get("streak", 0)),
        done_today=_is_today(doc.get("last_completed_at")),
        created_at=doc["created_at"],
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
            {"label": payload.label, "cadence": payload.cadence, "streak": 0, "last_completed_at": None},
        )
        return _habit_out(doc)

    async def update_habit(self, user_id: str, habit_id: str, payload: HabitUpdate) -> HabitOut:
        doc = await self._habits.update(habit_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Habit '{habit_id}' not found")
        return _habit_out(doc)

    async def toggle_habit(self, user_id: str, habit_id: str) -> HabitOut:
        """Mark today's completion on/off and adjust the streak accordingly."""
        current = await self._habits.get(habit_id, user_id)
        if current is None:
            raise NotFoundError(f"Habit '{habit_id}' not found")

        streak = int(current.get("streak", 0))
        if _is_today(current.get("last_completed_at")):
            patch = {"streak": max(0, streak - 1), "last_completed_at": None}
        else:
            patch = {"streak": streak + 1, "last_completed_at": datetime.now(timezone.utc)}

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
