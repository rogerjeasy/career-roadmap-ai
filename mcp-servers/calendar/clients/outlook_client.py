"""Microsoft Graph Calendar (Outlook) client.

Authentication: OAuth2 Bearer token supplied per-request by the calling agent.
The agent obtains the token through the Microsoft OAuth2 (MSAL) flow.

API reference: https://learn.microsoft.com/en-us/graph/api/resources/event
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

_GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


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
        logger.warning("outlook.unknown_tz", timezone=timezone_str)
        return ZoneInfo("UTC")


class OutlookClient(BaseCalendarClient):
    """Microsoft Graph Calendar (Outlook) client."""

    provider = CalendarProvider.OUTLOOK

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
        # Graph API expects naive datetime strings + separate timeZone field
        start_naive = start[:19]
        end_naive = end[:19]

        body: dict[str, Any] = {
            "subject": title,
            "body": {"contentType": "HTML", "content": description or ""},
            "start": {"dateTime": start_naive, "timeZone": timezone},
            "end": {"dateTime": end_naive, "timeZone": timezone},
            "isAllDay": all_day,
            "categories": ["Career Roadmap"],
        }
        if location:
            body["location"] = {"displayName": location}

        if reminder_minutes:
            # Outlook supports a single reminder; use the smallest value
            body["isReminderOn"] = True
            body["reminderMinutesBeforeStart"] = min(reminder_minutes)
        else:
            body["isReminderOn"] = False

        if calendar_id and calendar_id != "primary":
            url = f"{_GRAPH_BASE}/calendars/{calendar_id}/events"
        else:
            url = f"{_GRAPH_BASE}/events"

        resp = await self._post(url, headers=_auth_headers(access_token), json_body=body)
        return _parse_graph_event(resp.json())

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
        # Graph OData filter uses naive datetimes
        _time_min = (time_min or now.isoformat())[:19]
        _time_max = (time_max or (now + timedelta(days=30)).isoformat())[:19]

        filter_expr = (
            f"start/dateTime ge '{_time_min}' and start/dateTime le '{_time_max}'"
        )
        params: dict[str, Any] = {
            "$top": max_results,
            "$orderby": "start/dateTime",
            "$filter": filter_expr,
        }
        headers = {
            **_auth_headers(access_token),
            "Prefer": f'outlook.timezone="{timezone}"',
        }

        if calendar_id and calendar_id != "primary":
            url = f"{_GRAPH_BASE}/calendars/{calendar_id}/events"
        else:
            url = f"{_GRAPH_BASE}/events"

        resp = await self._get(url, headers=headers, params=params)
        items = resp.json().get("value", [])
        return [_parse_graph_event(item) for item in items]


def _parse_graph_event(data: dict[str, Any]) -> CalendarEvent:
    start_raw = data.get("start", {})
    end_raw = data.get("end", {})

    tz_str = start_raw.get("timeZone", "UTC")
    try:
        tz = ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")

    start_str = start_raw.get("dateTime", "")
    end_str = end_raw.get("dateTime", "")

    try:
        start_dt = datetime.fromisoformat(start_str).replace(tzinfo=tz)
    except ValueError:
        start_dt = datetime.now(timezone.utc)

    try:
        end_dt = datetime.fromisoformat(end_str).replace(tzinfo=tz)
    except ValueError:
        end_dt = start_dt

    created_raw = data.get("createdDateTime", "")
    created_dt: datetime | None = None
    if created_raw:
        try:
            # Graph returns ISO8601 with trailing Z
            created_dt = datetime.fromisoformat(created_raw.rstrip("Z") + "+00:00")
        except ValueError:
            pass

    is_reminder_on = data.get("isReminderOn", False)
    reminder_minutes: list[int] = []
    if is_reminder_on and "reminderMinutesBeforeStart" in data:
        reminder_minutes = [int(data["reminderMinutesBeforeStart"])]

    return CalendarEvent(
        id=data.get("id") or str(uuid.uuid4()),
        title=data.get("subject", ""),
        description=data.get("body", {}).get("content", ""),
        start=start_dt,
        end=end_dt,
        all_day=data.get("isAllDay", False),
        location=data.get("location", {}).get("displayName", ""),
        provider=CalendarProvider.OUTLOOK,
        html_link=data.get("webLink", ""),
        reminder_minutes=reminder_minutes,
        created_at=created_dt,
    )
