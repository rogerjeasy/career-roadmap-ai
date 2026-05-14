"""Pydantic data models for the Calendar MCP server.

No ORM coupling — pure Pydantic v2. Both Google Calendar and Outlook clients
normalise their provider-specific responses into ``CalendarEvent``.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CalendarProvider(StrEnum):
    GOOGLE = "google"
    OUTLOOK = "outlook"


# Google Calendar colorId → career task type mapping
GOOGLE_COLOR_BY_TASK_TYPE: dict[str, str] = {
    "learning": "7",      # Peacock (blue)
    "practice": "2",      # Sage (green)
    "milestone": "10",    # Tomato (red)
    "application": "5",   # Banana (yellow)
    "other": "9",         # Basil (dark green)
}


class CalendarEvent(BaseModel):
    """Normalised calendar event from any provider."""

    id: str
    title: str
    description: str = ""
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""
    provider: CalendarProvider
    html_link: str = ""
    calendar_id: str = "primary"
    reminder_minutes: list[int] = Field(default_factory=list)
    created_at: datetime | None = None

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
            "location": self.location,
            "provider": self.provider,
            "html_link": self.html_link,
            "calendar_id": self.calendar_id,
            "reminder_minutes": self.reminder_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Weekly task spec ──────────────────────────────────────────────────────────


class WeeklyTask(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)
    day_of_week: int = Field(
        ge=0, le=6, description="0=Monday, 1=Tuesday, ..., 6=Sunday"
    )
    start_time: str = Field(
        default="09:00",
        description="Start time in HH:MM format (24h)",
        pattern=r"^\d{2}:\d{2}$",
    )
    duration_minutes: int = Field(default=60, ge=15, le=480)
    task_type: Literal["learning", "practice", "application", "milestone", "other"] = "other"
    reminder_minutes: list[int] = Field(
        default_factory=list,
        description="Override reminder minutes; empty = use server default",
    )

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminders(cls, v: list[int]) -> list[int]:
        return [m for m in v if 0 <= m <= 10080]


# ── Tool parameter models ─────────────────────────────────────────────────────


class CreateEventParams(BaseModel):
    provider: CalendarProvider
    access_token: str = Field(
        default="",
        description="OAuth Bearer token. Optional when a token is stored server-side via store_oauth_token.",
    )
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)
    start_datetime: str = Field(
        description="ISO8601 datetime string e.g. '2026-05-11T09:00:00'"
    )
    end_datetime: str = Field(
        description="ISO8601 datetime string e.g. '2026-05-11T10:00:00'"
    )
    timezone: str = Field(default="UTC", description="IANA timezone e.g. 'America/New_York'")
    all_day: bool = False
    location: str = Field(default="", max_length=500)
    reminder_minutes: list[int] = Field(
        default_factory=list,
        description="Minutes before event to send reminders (e.g. [60, 10])",
    )
    calendar_id: str = Field(default="primary", description="'primary' for default calendar")
    color_id: str = Field(default="", description="Provider-specific color ID")

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminders(cls, v: list[int]) -> list[int]:
        return [m for m in v if 0 <= m <= 10080]


class CreateWeeklyTasksParams(BaseModel):
    provider: CalendarProvider
    access_token: str = Field(
        default="",
        description="OAuth Bearer token. Optional when a token is stored server-side via store_oauth_token.",
    )
    week_start: str = Field(
        description="ISO date for Monday of the target week e.g. '2026-05-11'",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    tasks: list[WeeklyTask] = Field(
        min_length=1,
        max_length=50,
        description="Career tasks to schedule for the week",
    )
    timezone: str = Field(default="UTC", description="IANA timezone for all events")
    default_reminder_minutes: list[int] = Field(
        default_factory=lambda: [60, 10],
        description="Reminders applied when a task's reminder_minutes is empty",
    )
    calendar_id: str = Field(default="primary")

    @field_validator("default_reminder_minutes")
    @classmethod
    def validate_reminders(cls, v: list[int]) -> list[int]:
        return [m for m in v if 0 <= m <= 10080]


class ListUpcomingParams(BaseModel):
    provider: CalendarProvider
    access_token: str = Field(
        default="",
        description="OAuth Bearer token. Optional when a token is stored server-side via store_oauth_token.",
    )
    max_results: int = Field(default=10, ge=1, le=100)
    time_min: str | None = Field(
        default=None,
        description="ISO8601 lower bound (inclusive). Defaults to now.",
    )
    time_max: str | None = Field(
        default=None,
        description="ISO8601 upper bound (exclusive). Defaults to 30 days from now.",
    )
    timezone: str = Field(default="UTC")
    calendar_id: str = Field(default="primary")


class StoreOAuthTokenParams(BaseModel):
    provider: CalendarProvider
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(default="")
    expires_in: int = Field(default=3600, ge=1, description="Token lifetime in seconds")


# ── Tool result models ────────────────────────────────────────────────────────


class CreateEventResult(BaseModel):
    event: dict[str, Any]
    provider: str
    created_at: str


class CreateWeeklyTasksResult(BaseModel):
    created_events: list[dict[str, Any]]
    failed_tasks: list[dict[str, Any]]
    total_requested: int
    total_created: int
    total_failed: int
    provider: str
    week_start: str


class ListUpcomingResult(BaseModel):
    events: list[dict[str, Any]]
    total_count: int
    provider: str
    time_min: str | None
    time_max: str | None
    fetched_at: str
