# MCP Calendar Server

Schedules career roadmap tasks and milestone reminders on **Google Calendar** and **Outlook (Microsoft Graph)**.

Port: **3006** (`MCP_CALENDAR_URL=http://mcp-calendar:3006`)

---

## Tools

| Method | Description |
|---|---|
| `create_event` | Create a single calendar event — milestones, reminders, one-off tasks |
| `create_weekly_tasks` | Bulk-create a week's roadmap tasks as calendar events with color-coding |
| `list_upcoming` | List upcoming events within a time window (cached 5 min) |

---

## Authentication

Both providers use **OAuth2 Bearer tokens supplied per-request** by the calling agent. The calendar server never stores tokens — the agent obtains them through the OAuth2 consent flow and passes them in each tool call via the `access_token` parameter.

The server itself is protected by `X-MCP-API-Key` (shared internal key).

---

## `create_event` params

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | `"google" \| "outlook"` | ✓ | — | Calendar provider |
| `access_token` | `str` | ✓ | — | OAuth Bearer token |
| `title` | `str` | ✓ | — | Event title (max 500 chars) |
| `start_datetime` | `str` | ✓ | — | ISO8601 e.g. `"2026-05-11T09:00:00"` |
| `end_datetime` | `str` | ✓ | — | ISO8601 e.g. `"2026-05-11T10:00:00"` |
| `timezone` | `str` | | `"UTC"` | IANA timezone e.g. `"Europe/Zurich"` |
| `description` | `str` | | `""` | Event body (max 5000 chars) |
| `all_day` | `bool` | | `false` | All-day event flag |
| `location` | `str` | | `""` | Location string |
| `reminder_minutes` | `list[int]` | | `[]` | Minutes before event e.g. `[60, 10]` |
| `calendar_id` | `str` | | `"primary"` | Calendar ID |
| `color_id` | `str` | | `""` | Google colorId (1–11) or Outlook category |

---

## `create_weekly_tasks` params

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | `"google" \| "outlook"` | ✓ | — | Calendar provider |
| `access_token` | `str` | ✓ | — | OAuth Bearer token |
| `week_start` | `str` | ✓ | — | ISO date for Monday e.g. `"2026-05-11"` |
| `tasks` | `list[WeeklyTask]` | ✓ | — | 1–50 tasks (see below) |
| `timezone` | `str` | | `"UTC"` | Applied to all events |
| `default_reminder_minutes` | `list[int]` | | `[60, 10]` | Reminders used when task doesn't override |
| `calendar_id` | `str` | | `"primary"` | Target calendar |

**WeeklyTask fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | `str` | ✓ | — | Task title |
| `day_of_week` | `int` | ✓ | — | 0=Mon … 6=Sun |
| `start_time` | `str` | | `"09:00"` | HH:MM (24h) |
| `duration_minutes` | `int` | | `60` | 15–480 min |
| `task_type` | `str` | | `"other"` | `learning \| practice \| application \| milestone \| other` |
| `description` | `str` | | `""` | Task description |
| `reminder_minutes` | `list[int]` | | `[]` | Overrides default_reminder_minutes |

**Color coding (Google Calendar):**

| task_type | Google colorId | Color |
|---|---|---|
| `learning` | 7 | Peacock (blue) |
| `practice` | 2 | Sage (green) |
| `milestone` | 10 | Tomato (red) |
| `application` | 5 | Banana (yellow) |
| `other` | 9 | Basil (dark green) |

---

## `list_upcoming` params

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | `"google" \| "outlook"` | ✓ | — | Calendar provider |
| `access_token` | `str` | ✓ | — | OAuth Bearer token |
| `max_results` | `int` | | `10` | 1–100 events |
| `time_min` | `str` | | now | ISO8601 lower bound |
| `time_max` | `str` | | +30 days | ISO8601 upper bound |
| `timezone` | `str` | | `"UTC"` | Display timezone |
| `calendar_id` | `str` | | `"primary"` | Calendar ID |

Results are cached for **5 minutes** per (user_id, provider, time range).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `MCP_API_KEY` | `""` | Shared key for X-MCP-API-Key auth (skipped if empty) |
| `REDIS_URL` | `redis://localhost:6379/6` | Cache + rate limiter |
| `CACHE_TTL_SECONDS` | `300` | list_upcoming cache TTL |
| `RATE_LIMIT_PER_MINUTE` | `30` | Per-user-per-tool rate limit |
| `HTTP_TIMEOUT_SECONDS` | `15` | Upstream API timeout |
| `PORT` | `3006` | Server port |

---

## Running locally

```bash
# From mcp-servers/calendar/
poetry install
uvicorn server:app --host 0.0.0.0 --port 3006 --reload
```

Health: `GET /livez`, `GET /readyz`
Metrics: `GET /metrics`

---

## Running tests

```bash
cd mcp-servers/calendar
poetry run pytest
```
