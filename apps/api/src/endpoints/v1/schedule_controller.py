"""Schedule — habits (with daily toggle) and weekly time blocks.

Routes:
  GET    /api/v1/schedule/habits             — list habits
  POST   /api/v1/schedule/habits             — create a habit
  PATCH  /api/v1/schedule/habits/{id}        — rename / re-cadence a habit
  POST   /api/v1/schedule/habits/{id}/toggle — toggle today's completion
  DELETE /api/v1/schedule/habits/{id}        — delete a habit
  GET    /api/v1/schedule/blocks             — list weekly time blocks
  POST   /api/v1/schedule/blocks             — create a time block
  DELETE /api/v1/schedule/blocks/{id}        — delete a time block
  GET    /api/v1/schedule/budget             — weekly budget (logged vs target hours)
  PUT    /api/v1/schedule/budget/targets     — set weekly target hours per category
  GET    /api/v1/schedule/time-logs          — list this week's logged-hours entries
  POST   /api/v1/schedule/time-logs          — log hours against a category
  DELETE /api/v1/schedule/time-logs/{id}     — delete a logged-hours entry
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.schedule.schemas import (
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
from src.domains.schedule.service import ScheduleService, get_schedule_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


# ── Habits ────────────────────────────────────────────────────────────────────

@router.get("/habits", response_model=list[HabitOut], summary="List habits")
async def list_habits(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[HabitOut]:
    return await service.list_habits(user.uid)


@router.post(
    "/habits",
    response_model=HabitOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a habit",
)
async def create_habit(
    body: HabitCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> HabitOut:
    return await service.create_habit(user.uid, body)


@router.patch("/habits/{habit_id}", response_model=HabitOut, summary="Update a habit")
async def update_habit(
    habit_id: str,
    body: HabitUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> HabitOut:
    return await service.update_habit(user.uid, habit_id, body)


@router.post(
    "/habits/{habit_id}/toggle",
    response_model=HabitOut,
    summary="Toggle today's completion for a habit",
)
async def toggle_habit(
    habit_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> HabitOut:
    return await service.toggle_habit(user.uid, habit_id)


@router.delete(
    "/habits/{habit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a habit",
)
async def delete_habit(
    habit_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> None:
    await service.delete_habit(user.uid, habit_id)


# ── Time blocks ─────────────────────────────────────────────────────────────--

@router.get("/blocks", response_model=list[ScheduleBlockOut], summary="List time blocks")
async def list_blocks(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleBlockOut]:
    return await service.list_blocks(user.uid)


@router.post(
    "/blocks",
    response_model=ScheduleBlockOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a time block",
)
async def create_block(
    body: ScheduleBlockCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> ScheduleBlockOut:
    return await service.create_block(user.uid, body)


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a time block",
)
async def delete_block(
    block_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> None:
    await service.delete_block(user.uid, block_id)


# ── Weekly time budget ────────────────────────────────────────────────────────

@router.get("/budget", response_model=BudgetOut, summary="Get the weekly time budget")
async def get_budget(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> BudgetOut:
    return await service.get_budget(user.uid)


@router.put(
    "/budget/targets",
    response_model=BudgetOut,
    summary="Set weekly target hours per category",
)
async def set_budget_targets(
    body: BudgetTargets,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> BudgetOut:
    return await service.set_budget_targets(user.uid, body)


@router.get(
    "/time-logs",
    response_model=list[TimeLogOut],
    summary="List this week's logged-hours entries",
)
async def list_time_logs(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[TimeLogOut]:
    return await service.list_time_logs(user.uid)


@router.post(
    "/time-logs",
    response_model=TimeLogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log hours against a category",
)
async def create_time_log(
    body: TimeLogCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> TimeLogOut:
    return await service.log_time(user.uid, body)


@router.delete(
    "/time-logs/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a logged-hours entry",
)
async def delete_time_log(
    log_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> None:
    await service.delete_time_log(user.uid, log_id)
