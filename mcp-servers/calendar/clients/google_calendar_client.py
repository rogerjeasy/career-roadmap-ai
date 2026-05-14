"""Google Calendar REST API v3 client.

Authentication: OAuth2 Bearer token supplied per-request by the calling agent.
The agent obtains the token through the Google OAuth2 flow in the API layer.

API reference: https://developers.google.com/calendar/api/v3/reference
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from clients.base_client import BaseCalendarClient
from models import CalendarEvent, CalendarProvider

logger = structlog.get_logger(__name__)

_GOOGLE_API_BASE = "https://www.googleapis.com/calendar/v3"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _safe_tz(timezone_str: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_str)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning("google_calendar.unknown_tz", timezone=timezone_str)
        return ZoneInfo("UTC")


class GoogleCalendarClient(BaseCalendarClient):
    """Google Calendar API v3 client."""

    provider = CalendarProvider.GOOGLE

    async def _create_event(
        self,
        *,
        access_token: str,
        title: str,
        description: str,
        start: str,
        end: str,
        timezone: str,
        all_day: bool,
        location: str,
        reminder_minutes: list[int],
        calendar_id: str,
        color_id: str,
        correlation_id: str,
    ) -> CalendarEvent:
        if all_day:
            # All-day events use date-only strings
            start_field: dict[str, str] = {"date": start[:10]}
            end_field: dict[str, str] = {"date": end[:10]}
        else:
            start_field = {"dateTime": start, "timeZone": timezone}
            end_field = {"dateTime": end, "timeZone": timezone}

        body: dict[str, Any] = {
            "summary": title,
            "description": description,
            "start": start_field,
            "end": end_field,
        }
        if location:
            body["location"] = location
        if color_id:
            body["colorId"] = color_id

        if reminder_minutes:
            body["reminders"] = {
                "useDefault": False,
                # Google supports up to 5 reminder overrides
                "overrides": [
                    {"method": "popup", "minutes": m} for m in reminder_minutes[:5]
                ],
            }
        else:
            body["reminders"] = {"useDefault": True}

        url = f"{_GOOGLE_API_BASE}/calendars/{calendar_id}/events"
        resp = await self._post(url, headers=_auth_headers(access_token), json_body=body)
        return _parse_google_event(resp.json())

    async def _list_upcoming(
        self,
        *,
        access_token: str,
        max_results: int,
        time_min: str | None,
        time_max: str | None,
        timezone: str,
        calendar_id: str,
        correlation_id: str,
    ) -> list[CalendarEvent]:
        now = datetime.now(tz=ZoneInfo("UTC"))
        _time_min = time_min or now.isoformat()
        _time_max = time_max or (now + timedelta(days=30)).isoformat()

        params: dict[str, Any] = {
            "maxResults": max_results,
            "orderBy": "startTime",
            "singleEvents": "true",
            "timeMin": _time_min,
            "timeMax": _time_max,
            "timeZone": timezone,
        }

        url = f"{_GOOGLE_API_BASE}/calendars/{calendar_id}/events"
        resp = await self._get(url, headers=_auth_headers(access_token), params=params)
        items = resp.json().get("items", [])
        return [_parse_google_event(item) for item in items]


def _parse_google_event(data: dict[str, Any]) -> CalendarEvent:
    start_raw = data.get("start", {})
    end_raw = data.get("end", {})
    all_day = "date" in start_raw and "dateTime" not in start_raw

    if all_day:
        start_dt = datetime.fromisoformat(start_raw["date"]).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_raw["date"]).replace(tzinfo=timezone.utc)
    else:
        start_dt = datetime.fromisoformat(start_raw.get("dateTime", "1970-01-01T00:00:00+00:00"))
        end_dt = datetime.fromisoformat(end_raw.get("dateTime", "1970-01-01T00:00:00+00:00"))

    created_raw = data.get("created")
    created_dt: datetime | None = None
    if created_raw:
        try:
            created_dt = datetime.fromisoformat(created_raw)
        except ValueError:
            pass

    # Extract reminder overrides if present
    reminders_data = data.get("reminders", {})
    reminder_minutes: list[int] = []
    if not reminders_data.get("useDefault", True):
        for override in reminders_data.get("overrides", []):
            reminder_minutes.append(int(override.get("minutes", 0)))

    return CalendarEvent(
        id=data.get("id") or str(uuid.uuid4()),
        title=data.get("summary", ""),
        description=data.get("description", ""),
        start=start_dt,
        end=end_dt,
        all_day=all_day,
        location=data.get("location", ""),
        provider=CalendarProvider.GOOGLE,
        html_link=data.get("htmlLink", ""),
        calendar_id=data.get("organizer", {}).get("email", "primary"),
        reminder_minutes=reminder_minutes,
        created_at=created_dt,
    )
