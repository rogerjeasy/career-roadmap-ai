# L4 — Calendar MCP Server

## 1. Context and Purpose

The Calendar MCP Server is the fourth implemented component of the **L4 MCP Tool Server** layer. It sits between the L3 Specialist Agents and two external calendar providers (Google Calendar and Microsoft Outlook), acting as the sole broker for all calendar read/write operations.

```
L3 Agents (Roadmap Generation, Progress Adaptation, Conversational Coach)
    │
    │  mcp.call("calendar", "create_weekly_tasks", {...})
    │  JSON-RPC 2.0 over HTTP  ─── X-MCP-API-Key ─── X-Correlation-ID
    ▼
┌──────────────────────────────────────────────────────────────────┐
│              Calendar MCP Server  :3006                          │
│                                                                  │
│  POST /   ─── dispatcher ───► create_event                       │
│                           ───► create_weekly_tasks               │
│                           ───► list_upcoming                     │
│  GET /livez  GET /readyz  GET /metrics                           │
└─────────────┬────────────────────────────────────────────────────┘
              │  OAuth2 Bearer token per request
    ┌─────────┴──────────────┐
    ▼                        ▼
Google Calendar API v3   Microsoft Graph API
(calendar.google.com)    (graph.microsoft.com)
```

Agents never call calendar APIs directly. All write operations (event creation) require an OAuth2 token supplied by the calling agent, which obtains it through the consent flow in the API layer. The calendar server never stores tokens — it acts as a stateless proxy that enforces rate limiting, caching, observability, and audit logging at this layer.

The primary use case is **writing a weekly roadmap schedule**: the Roadmap Generation Agent computes a week-by-week career plan and the Calendar server places each task as a real calendar event, color-coded by task type, with configurable reminders. Users receive a concrete, actionable schedule in the calendar app they already use.

---

## 2. File Structure

```
mcp-servers/
├── shared/                              ← reused by all MCP servers
│   ├── __init__.py
│   ├── auth.py                          ← X-MCP-API-Key HMAC validation
│   ├── cache.py                         ← Redis response cache (SHA-256 keyed)
│   ├── rate_limiter.py                  ← sliding-window per-(user, tool) limiter
│   ├── error_handler.py                 ← JSON-RPC 2.0 error codes + builders
│   └── base_server.py                   ← _configure_logging(), _configure_tracing()
│
└── calendar/
    ├── pyproject.toml                   ← Poetry dependencies (port 3006)
    ├── config.py                        ← CalendarSettings (pydantic-settings)
    ├── models.py                        ← Pydantic data models
    ├── observability.py                 ← Prometheus metrics + get_tracer()
    ├── server.py                        ← entry point, lifespan, dispatcher
    │
    ├── clients/
    │   ├── __init__.py
    │   ├── base_client.py               ← BaseCalendarClient (abstract, OTel, metrics)
    │   ├── google_calendar_client.py    ← Google Calendar REST API v3
    │   └── outlook_client.py            ← Microsoft Graph Calendar API
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── create_event.py              ← single event creation handler
    │   ├── create_weekly_tasks.py       ← bulk weekly task scheduling handler
    │   └── list_upcoming.py             ← upcoming events list handler (cached)
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py                  ← sys.path setup + shared fixtures
        └── test_server.py               ← 18 tests (tools, errors, edge cases)
```

---

## 3. JSON-RPC 2.0 Protocol

### Transport

All requests are `POST /` with `Content-Type: application/json`. The server speaks plain JSON-RPC 2.0 — no WebSocket, no SSE.

**Request envelope:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "create_weekly_tasks",
  "params": { ... }
}
```

**Success response:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "result": { ... }
}
```

**Error response:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "error": {
    "code": -32602,
    "message": "Invalid create_weekly_tasks parameters",
    "data": [ ... ]
  }
}
```

HTTP status is always `200 OK` — errors are expressed in the JSON body per the JSON-RPC spec.

### Error Codes

| Code | Name | Meaning |
|------|------|---------|
| `-32700` | `PARSE_ERROR` | Request body is not valid JSON |
| `-32600` | `INVALID_REQUEST` | Missing `jsonrpc: "2.0"` or `method` |
| `-32601` | `METHOD_NOT_FOUND` | Unknown method name |
| `-32602` | `INVALID_PARAMS` | Pydantic validation failure on params |
| `-32603` | `INTERNAL_ERROR` | Unexpected server exception |
| `-32000` | `RATE_LIMITED` | Per-user sliding window exceeded |
| `-32001` | `UNAUTHORIZED` | Invalid or missing `X-MCP-API-Key` |
| `-32002` | `UPSTREAM_ERROR` | Provider not configured, 401/403 from API, or other upstream failure |
| `-32003` | `TOOL_TIMEOUT` | Upstream API request timed out |
| `-32004` | `CACHE_ERROR` | Redis operation failure |

### Request Headers

| Header | Required | Purpose |
|--------|----------|---------|
| `X-MCP-API-Key` | When `MCP_API_KEY` is set | Server authentication |
| `X-Correlation-ID` | No | Propagated into all logs and OTel spans |
| `X-User-ID` | No | Used as rate-limit key and cache key namespace (falls back to `"anonymous"`) |

---

## 4. Tools

### 4.1 `create_event`

Creates a single calendar event on Google Calendar or Outlook. Used for one-off milestones, deadline reminders, and flagged dates that don't belong to a weekly batch (e.g., "Apply to 5 jobs by this date", "Finish capstone project").

**Params — `CreateEventParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `"google" \| "outlook"` | required | Calendar provider |
| `access_token` | `str` (min 1 char) | required | OAuth2 Bearer token for the user |
| `title` | `str` (1–500 chars) | required | Event summary / title |
| `start_datetime` | `str` | required | ISO8601 datetime e.g. `"2026-05-11T09:00:00"` |
| `end_datetime` | `str` | required | ISO8601 datetime e.g. `"2026-05-11T10:00:00"` |
| `timezone` | `str` | `"UTC"` | IANA timezone e.g. `"America/New_York"`, `"Europe/Zurich"` |
| `description` | `str` (max 5000 chars) | `""` | Event body / notes |
| `all_day` | `bool` | `false` | All-day event flag (uses date-only in API calls) |
| `location` | `str` (max 500 chars) | `""` | Location string |
| `reminder_minutes` | `list[int]` | `[]` | Minutes before event to send reminders e.g. `[60, 10]` |
| `calendar_id` | `str` | `"primary"` | Target calendar ID (`"primary"` selects the user's default) |
| `color_id` | `str` | `""` | Provider-specific color (Google: `"1"`–`"11"`, Outlook: category name) |

**Result — `CreateEventResult`:**
```json
{
  "event": {
    "id": "google_event_abc123",
    "title": "Milestone: Week 3 Complete",
    "start": "2026-05-11T09:00:00+00:00",
    "end": "2026-05-11T09:30:00+00:00",
    "provider": "google",
    "html_link": "https://calendar.google.com/event?eid=abc123",
    "reminder_minutes": [60, 10],
    ...
  },
  "provider": "google",
  "created_at": "2026-05-11T08:55:00+00:00"
}
```

**Cache:** No caching (write operation).  
**Rate limit:** 30 calls / minute / user.

**Request lifecycle:**
```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Look up client by provider → UPSTREAM_ERROR if not configured
4. client.create_event(...) → raises on upstream 4xx/5xx
   └─ google: POST /calendars/{id}/events
   └─ outlook: POST /me/events (or /me/calendars/{id}/events)
5. Wrap result in CreateEventResult
6. Emit audit log + metrics → return result
```

---

### 4.2 `create_weekly_tasks`

The primary scheduling tool. Converts a list of weekly career tasks into real calendar events in a single batch call. The Roadmap Generation Agent calls this once per week when the user accepts their roadmap.

Each task specifies the day of the week (0=Mon … 6=Sun), start time, duration, and task type. The server computes the actual datetime by adding `day_of_week` days to `week_start` (the Monday of the target week), then calls the upstream provider for each event concurrently (max 5 in parallel).

**Params — `CreateWeeklyTasksParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `"google" \| "outlook"` | required | Calendar provider |
| `access_token` | `str` | required | OAuth2 Bearer token |
| `week_start` | `str` (ISO date) | required | Monday of the target week e.g. `"2026-05-11"` |
| `tasks` | `list[WeeklyTask]` (1–50) | required | Career tasks to schedule (see below) |
| `timezone` | `str` | `"UTC"` | Applied to all events |
| `default_reminder_minutes` | `list[int]` | `[60, 10]` | Reminders used when a task's `reminder_minutes` is empty |
| `calendar_id` | `str` | `"primary"` | Target calendar |

**`WeeklyTask` fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` (1–500 chars) | required | Task title e.g. "Complete React fundamentals module" |
| `day_of_week` | `int` (0–6) | required | 0=Monday, 6=Sunday |
| `start_time` | `str` (HH:MM) | `"09:00"` | 24h time string |
| `duration_minutes` | `int` (15–480) | `60` | Event duration |
| `task_type` | `"learning" \| "practice" \| "application" \| "milestone" \| "other"` | `"other"` | Determines Google Calendar color |
| `description` | `str` (max 5000 chars) | `""` | Task notes or learning objectives |
| `reminder_minutes` | `list[int]` | `[]` | Overrides `default_reminder_minutes` for this task only |

**Result — `CreateWeeklyTasksResult`:**
```json
{
  "created_events": [ ... ],
  "failed_tasks": [
    { "title": "Build REST API", "day_of_week": 2, "error": "API quota exceeded" }
  ],
  "total_requested": 7,
  "total_created": 6,
  "total_failed": 1,
  "provider": "google",
  "week_start": "2026-05-11"
}
```

The tool never hard-fails on partial batch errors — it always returns the `created_events` and `failed_tasks` separately. The agent can retry failed tasks or surface them to the user.

**Cache:** No caching (write operation).  
**Rate limit:** 30 calls / minute / user.

**Request lifecycle:**
```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. date.fromisoformat(week_start) → INVALID_PARAMS on bad date
4. ZoneInfo(timezone) → falls back to UTC on unknown tz (warn)
5. Build event_kwargs list: for each task
   - event_date = week_start_date + timedelta(days=task.day_of_week)
   - start_dt = datetime(event_date, HH, MM, tzinfo=tz)
   - end_dt = start_dt + timedelta(minutes=duration)
   - color_id = GOOGLE_COLOR_BY_TASK_TYPE[task_type]
6. client.create_events_batch(access_token, events, correlation_id)
   └─ asyncio.Semaphore(5): max 5 concurrent API calls
   └─ failures collected individually → do not cancel siblings
7. Build CreateWeeklyTasksResult (created + failed)
8. Emit audit log + metrics → return result
```

**Google Calendar color assignment by task type:**

| `task_type` | `colorId` | Color |
|-------------|-----------|-------|
| `learning` | `7` | Peacock (blue) |
| `practice` | `2` | Sage (green) |
| `milestone` | `10` | Tomato (red) |
| `application` | `5` | Banana (yellow) |
| `other` | `9` | Basil (dark green) |

Outlook does not support per-event color IDs; all events are assigned the `"Career Roadmap"` category, which the user can configure to a color in Outlook.

---

### 4.3 `list_upcoming`

Lists upcoming calendar events within a configurable time window. Used by the Conversational Coach and Progress Adaptation agents to read the user's schedule before suggesting changes or checking adherence.

Results are cached per (user_id, provider, time range, calendar_id) with a 5-minute TTL. The access token is excluded from the cache key to prevent token leakage into Redis keys.

**Params — `ListUpcomingParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `"google" \| "outlook"` | required | Calendar provider |
| `access_token` | `str` | required | OAuth2 Bearer token |
| `max_results` | `int` (1–100) | `10` | Maximum events to return |
| `time_min` | `str \| null` | now | ISO8601 lower bound (inclusive) |
| `time_max` | `str \| null` | now+30d | ISO8601 upper bound (exclusive) |
| `timezone` | `str` | `"UTC"` | Display timezone for the results |
| `calendar_id` | `str` | `"primary"` | Calendar ID to read from |

**Result — `ListUpcomingResult`:**
```json
{
  "events": [
    {
      "id": "google_event_xyz",
      "title": "Complete React fundamentals module",
      "start": "2026-05-11T09:00:00+02:00",
      "end": "2026-05-11T10:00:00+02:00",
      "provider": "google",
      "all_day": false,
      "reminder_minutes": [60, 10],
      ...
    }
  ],
  "total_count": 7,
  "provider": "google",
  "time_min": "2026-05-11T00:00:00+00:00",
  "time_max": "2026-06-10T00:00:00+00:00",
  "fetched_at": "2026-05-11T08:00:00+00:00"
}
```

**Cache TTL:** 5 minutes (keyed by user_id + provider + time range + calendar_id; access_token excluded).  
**Rate limit:** 30 calls / minute / user.

**Request lifecycle:**
```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Cache lookup (key excludes access_token) → return cached if hit
4. client.list_upcoming(...)
   └─ google: GET /calendars/{id}/events?singleEvents=true&orderBy=startTime
   └─ outlook: GET /me/events?$filter=start/dateTime ge ... and ...
5. Build ListUpcomingResult
6. Write to cache (TTL 300 s)
7. Emit audit log + metrics → return result
```

---

## 5. Data Models

### `CalendarEvent`

The canonical normalised representation returned by all clients. Every provider-specific response is mapped to this shape before leaving the client layer.

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Provider-specific event ID or UUID fallback |
| `title` | `str` | Event summary / subject |
| `description` | `str` | Event body / notes |
| `start` | `datetime` | Timezone-aware datetime |
| `end` | `datetime` | Timezone-aware datetime |
| `all_day` | `bool` | True for all-day events (date-only in provider APIs) |
| `location` | `str` | Location string if set |
| `provider` | `CalendarProvider` | `"google"` or `"outlook"` |
| `html_link` | `str` | Web link to open the event in the provider UI |
| `calendar_id` | `str` | Calendar this event belongs to |
| `reminder_minutes` | `list[int]` | Minutes before event for reminders |
| `created_at` | `datetime \| None` | UTC creation timestamp from provider |

**`model_dump_api()` output** serialises all datetimes as ISO 8601 strings and is the exact shape returned in tool results.

### `WeeklyTask`

Used only as a nested param model within `CreateWeeklyTasksParams`. Converted to `create_event` kwargs by `_build_event_kwargs()` in `create_weekly_tasks.py` — it never appears in tool results.

### Enums

**`CalendarProvider`:**

| Value | Provider |
|-------|----------|
| `"google"` | Google Calendar (REST API v3) |
| `"outlook"` | Microsoft Outlook (Microsoft Graph) |

### Tool Parameter Models

| Model | Used by |
|-------|---------|
| `CreateEventParams` | `create_event` |
| `CreateWeeklyTasksParams` | `create_weekly_tasks` |
| `ListUpcomingParams` | `list_upcoming` |

### Tool Result Models

| Model | Used by |
|-------|---------|
| `CreateEventResult` | `create_event` |
| `CreateWeeklyTasksResult` | `create_weekly_tasks` |
| `ListUpcomingResult` | `list_upcoming` |

---

## 6. API Providers

### Google Calendar REST API v3

- **Auth:** `Authorization: Bearer {access_token}` header
- **Base URL:** `https://www.googleapis.com/calendar/v3`
- **Create event:** `POST /calendars/{calendarId}/events`
- **List events:** `GET /calendars/{calendarId}/events`

**Create event body (non-all-day):**
```json
{
  "summary": "Complete React fundamentals module",
  "description": "Work through chapters 1–5 of the React docs",
  "start": { "dateTime": "2026-05-11T09:00:00", "timeZone": "Europe/Zurich" },
  "end":   { "dateTime": "2026-05-11T10:00:00", "timeZone": "Europe/Zurich" },
  "colorId": "7",
  "reminders": {
    "useDefault": false,
    "overrides": [
      { "method": "popup", "minutes": 60 },
      { "method": "popup", "minutes": 10 }
    ]
  }
}
```

**List events params:** `maxResults`, `orderBy=startTime`, `singleEvents=true`, `timeMin`, `timeMax`, `timeZone`

**All-day events:** Use `"date": "YYYY-MM-DD"` instead of `"dateTime"` in `start` and `end`.

**Reminders:** Google supports up to 5 `popup` override reminders per event. When `reminder_minutes` is empty, `"useDefault": true` is used instead.

**`colorId` reference (career task types):**

| colorId | Name | Hex |
|---------|------|-----|
| `2` | Sage | #33B679 (green) |
| `5` | Banana | #F6BF26 (yellow) |
| `7` | Peacock | #039BE5 (blue) |
| `9` | Basil | #0F9D58 (dark green) |
| `10` | Tomato | #D50000 (red) |

---

### Microsoft Graph Calendar API

- **Auth:** `Authorization: Bearer {access_token}` header
- **Base URL:** `https://graph.microsoft.com/v1.0/me`
- **Create event (default calendar):** `POST /events`
- **Create event (specific calendar):** `POST /calendars/{calendarId}/events`
- **List events:** `GET /events` or `GET /calendars/{calendarId}/events`

**Create event body:**
```json
{
  "subject": "Complete React fundamentals module",
  "body": { "contentType": "HTML", "content": "Work through chapters 1–5" },
  "start": { "dateTime": "2026-05-11T09:00:00", "timeZone": "Europe/Zurich" },
  "end":   { "dateTime": "2026-05-11T10:00:00", "timeZone": "Europe/Zurich" },
  "isAllDay": false,
  "categories": ["Career Roadmap"],
  "isReminderOn": true,
  "reminderMinutesBeforeStart": 10
}
```

**List events params:** `$top`, `$orderby=start/dateTime`, `$filter` (OData), `Prefer: outlook.timezone="{tz}"` header

**Reminder limitation:** Microsoft Graph supports only **one** reminder value per event (`reminderMinutesBeforeStart: int`). When `reminder_minutes` has multiple values, the **smallest** is used (closest to the event). Users who want multiple reminders must configure them manually in Outlook.

**Datetime format:** Graph requires naive datetime strings (no timezone offset) with a separate `timeZone` field, unlike Google which accepts RFC3339 with offset. The Outlook client strips offsets using `start[:19]` before sending.

**Response parsing (`_parse_graph_event`):** `createdDateTime` from Graph always has a trailing `Z` (UTC), which Python's `datetime.fromisoformat()` does not handle before 3.11 — the client normalises it to `+00:00` before parsing.

---

## 7. Shared Modules

All shared modules are identical to those used by the Job Board, Course Catalogue, and Social Signals MCP Servers. See `l4-job-board-mcp-server.md § 7. Shared Modules` for the full reference.

### `shared/error_handler.py`
`JsonRpcErrorCode` enum + `make_success_response()` / `make_error_response()` builders. `JsonRpcError` is raised by tool handlers to signal a well-formed error without triggering the generic 500 handler.

### `shared/auth.py`
`verify_api_key()` compares `X-MCP-API-Key` against `MCP_API_KEY` using `hmac.compare_digest` (constant-time, prevents timing attacks). Bypassed when `MCP_API_KEY` is empty — the intended dev workflow.

### `shared/cache.py`
`ResponseCache` wraps `redis.asyncio`. Cache keys:
```
mcp:cache:{tool}:{sha256(json({tool, params}))[:16]}
```
The access token is excluded from the cache key for `list_upcoming` to prevent user credentials appearing in Redis key names. Redis failures are caught and logged; the caller proceeds without cache.

### `shared/rate_limiter.py`
Sliding-window limiter per `(user_id, tool)` using Redis sorted sets. Fails open when Redis is unavailable so a cache outage does not block agents.

---

## 8. Client Architecture

### `BaseCalendarClient`

Both clients inherit from this abstract class. It provides:

- **`create_event(...)` public method:** wraps `_create_event` with OTel spans, Prometheus recording, and structured logging; raises on any failure (callers handle errors)
- **`create_events_batch(access_token, events)` public method:** creates events concurrently using `asyncio.gather` with a `Semaphore(5)` cap; collects failures individually without cancelling successful siblings
- **`list_upcoming(...)` public method:** wraps `_list_upcoming` with OTel spans and Prometheus recording; raises on failure
- **`_get(url, headers, **kwargs)` / `_post(url, headers, json_body)` HTTP helpers:** create a fresh `httpx.AsyncClient` per call (no persistent connection pool needed for low-frequency calendar operations)

```python
# Each batch event creation is isolated:
async def _try_create(event_kwargs):
    day_of_week = event_kwargs.pop("_day_of_week", -1)
    async with semaphore:
        try:
            return await self.create_event(**event_kwargs, access_token=token)
        except Exception as exc:
            failed.append({"title": ..., "day_of_week": day_of_week, "error": str(exc)})
            return None
```

Subclasses implement `_create_event` and `_list_upcoming`, which map between the normalised `CalendarEvent` model and the provider-specific API format.

### Per-Call HTTP Clients vs. Persistent

Unlike the Job Board and Social Signals clients which use a persistent `httpx.AsyncClient` across requests (via `__aenter__`/`__aexit__`), the Calendar clients create a new `httpx.AsyncClient` per API call. The rationale:

- Calendar operations are low-frequency (typically one batch per week per user), unlike job search which may receive dozens of concurrent agent calls
- OAuth tokens can change between calls (refresh), so there is no benefit to re-using a connection authenticated with a token that may have been revoked
- Per-call clients simplify the lifecycle — no context manager required at server startup

---

## 9. Observability

### Prometheus Metrics

All metrics are prefixed `mcp_calendar_`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_calendar_event_create_total` | Counter | `provider`, `status` | Upstream event creation calls by provider and outcome |
| `mcp_calendar_event_create_duration_seconds` | Histogram | `provider` | Event creation latency per provider |
| `mcp_calendar_weekly_tasks_total` | Counter | `provider`, `status` | `create_weekly_tasks` calls by provider and outcome |
| `mcp_calendar_weekly_tasks_created_count` | Histogram | `provider` | Events successfully created per batch |
| `mcp_calendar_list_fetch_total` | Counter | `provider`, `status` | `list_upcoming` upstream calls by provider and outcome |
| `mcp_calendar_list_fetch_results_count` | Histogram | `provider` | Events returned per `list_upcoming` call |
| `mcp_calendar_cache_hits_total` | Counter | `tool` | Cache hits by tool |
| `mcp_calendar_cache_misses_total` | Counter | `tool` | Cache misses by tool |
| `mcp_calendar_rate_limit_hit_total` | Counter | `tool` | Rate-limited requests by tool |
| `mcp_calendar_tool_call_total` | Counter | `method`, `status` | Tool invocations by method and outcome |
| `mcp_calendar_tool_call_duration_seconds` | Histogram | `method` | End-to-end tool call latency |
| `mcp_calendar_audit_log_total` | Counter | `tool` | Audit log events emitted |

Status labels for `event_create_total`: `success`, `http_error`, `auth_error`, `error`  
Status labels for `tool_call_total`: `ok`, `cache_hit`, `rpc_error`, `error`, `rate_limited`

### OpenTelemetry Spans

| Span Name | Created by | Attributes |
|-----------|------------|------------|
| `tool.create_event` | `create_event.py` | `user_id`, `correlation_id`, `provider`, `event_id` |
| `tool.create_weekly_tasks` | `create_weekly_tasks.py` | `user_id`, `correlation_id`, `provider`, `task_count`, `created_count`, `failed_count` |
| `tool.list_upcoming` | `list_upcoming.py` | `user_id`, `correlation_id`, `provider`, `result_count` |
| `calendar.{provider}.create_event` | `base_client.py` | `provider`, `correlation_id`, `event_id`, `latency_ms` |
| `calendar.{provider}.list_upcoming` | `base_client.py` | `provider`, `correlation_id`, `result_count`, `latency_ms` |

OTLP export is enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. In development, spans are printed to stdout via `ConsoleSpanExporter`.

### Structured Logging

All logs use `structlog` with keyword arguments. Key events:

```python
logger.info("calendar.providers_registered", providers=["google", "outlook"])
logger.info("create_event.completed", provider=..., event_id=..., title=..., user_id=..., correlation_id=...)
logger.info("create_weekly_tasks.completed", provider=..., week_start=..., total_requested=7, total_created=6, total_failed=1, ...)
logger.info("list_upcoming.completed", provider=..., count=7, user_id=..., correlation_id=...)
logger.warning("calendar.create_event_http_error", provider=..., status_code=401, error=..., correlation_id=...)
```

Format: JSON in production (`ENVIRONMENT != "development"`), coloured console in dev.

### Health Endpoints

```
GET /livez   → 200 {"status": "ok"}
GET /readyz  → 200 {"status": "ok", "server_id": "calendar", "providers": ["google", "outlook"]}
GET /metrics → 200 (Prometheus text format)
```

---

## 10. Configuration Reference

All values are loaded from environment variables via `CalendarSettings` (pydantic-settings). A `.env` file is supported in development.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENVIRONMENT` | `development` | No | `development`, `staging`, `production` |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HOST` | `0.0.0.0` | No | Bind address for uvicorn |
| `PORT` | `3006` | No | Listen port |
| `MCP_API_KEY` | `""` | No | Shared secret for `X-MCP-API-Key` auth (empty = bypass in dev) |
| `REDIS_URL` | `redis://localhost:6379/6` | No | Redis DSN (DB 6 — separate from other MCP servers) |
| `CACHE_TTL_SECONDS` | `300` | No | `list_upcoming` cache TTL in seconds (5 minutes) |
| `RATE_LIMIT_PER_MINUTE` | `30` | No | Max requests per user per minute (lower than social signals — calendar ops are heavier) |
| `HTTP_TIMEOUT_SECONDS` | `15.0` | No | Per-provider request timeout |
| `HTTP_MAX_RETRIES` | `3` | No | Max retries (not currently auto-applied; reserved for future retry decorator) |
| `DEFAULT_REMINDER_MINUTES` | `[60, 10]` | No | Server-level default reminders applied via `create_weekly_tasks.default_reminder_minutes` |
| `MAX_EVENTS_PER_WEEK` | `50` | No | Soft cap on tasks accepted per `create_weekly_tasks` call (enforced by model `max_length=50`) |
| `MAX_LIST_RESULTS` | `50` | No | Soft cap on `list_upcoming` results |
| `DEFAULT_TIMEZONE` | `"UTC"` | No | Fallback timezone when none is provided |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | No | OTLP gRPC endpoint for trace export |

The Redis DB index is `6` to avoid colliding with other MCP servers on the same Redis instance (job-board=1, course-catalogue=2, github-trends=3, salary-benchmark=4, social-signals=5).

Neither Google nor Microsoft credentials are stored in this server's environment — OAuth tokens are **per-request parameters** passed by the calling agent.

---

## 11. Agent Integration

The agents layer connects via `HttpMCPClient`. Three agents use this server:

### Roadmap Generation Agent

Primary writer. After generating a week-by-week career plan, calls `create_weekly_tasks` for each week the user accepts to schedule all tasks on the user's calendar. Passes the Roadmap agent's task list directly as `WeeklyTask` objects.

```python
result = await mcp_client.call(
    "calendar",
    "create_weekly_tasks",
    {
        "provider": user_context.calendar_provider,     # "google" or "outlook"
        "access_token": user_context.calendar_token,   # from OAuth consent
        "week_start": "2026-05-11",
        "timezone": user_context.timezone,
        "tasks": [
            {
                "title": "Complete React fundamentals: components & hooks",
                "day_of_week": 0,  # Monday
                "start_time": "09:00",
                "duration_minutes": 90,
                "task_type": "learning",
                "description": "Cover sections 1.1–1.4 of the React docs",
            },
            ...
        ],
        "default_reminder_minutes": [60, 10],
    },
    correlation_id=correlation_id,
)
# result["total_created"] → number of events successfully added to calendar
# result["failed_tasks"]  → tasks that failed (retry or surface to user)
```

Configured via `MCP_CALENDAR_URL` in the agents `.env`.

### Conversational Coach Agent

Reader. Before responding to a progress check-in, calls `list_upcoming` to fetch the user's next 7 days of career events. Uses this to generate contextually aware suggestions ("I see you have 'Submit job application' scheduled for Thursday — have you tailored your CV for this specific role?").

```python
events = await mcp_client.call(
    "calendar",
    "list_upcoming",
    {
        "provider": user_context.calendar_provider,
        "access_token": user_context.calendar_token,
        "max_results": 20,
        "time_min": today.isoformat(),
        "time_max": (today + timedelta(days=7)).isoformat(),
        "timezone": user_context.timezone,
    },
    correlation_id=correlation_id,
)
```

### Progress Adaptation Agent

Writer. When the agent detects that a user is consistently completing tasks ahead of schedule (or falling behind), it calls `create_event` to add a milestone event flagging the adaptation ("Roadmap re-calibrated: accelerating Week 5 based on your progress") and may call `create_weekly_tasks` with an updated task list for the revised week.

### Consent requirement

The CLAUDE.md architecture mandates explicit user consent before connecting external accounts. Calendar integration requires the user to go through the Google OAuth or Microsoft MSAL flow in the API layer first. The `user_context.calendar_token` and `user_context.calendar_provider` fields are only populated after consent is granted. Agents check for their presence before calling this server, and surface a consent prompt if they are absent.

### Stub fallback

When `MCP_CALENDAR_URL` is not set, agents use `StubMCPClient` which returns mock `CreateWeeklyTasksResult` / `ListUpcomingResult` objects without any network calls.

---

## 12. Path Resolution

The `calendar/` directory is a valid Python identifier but is treated as a flat module package for consistency with the other MCP servers. Imports within the server use flat module names (e.g., `from models import CalendarEvent`, `from clients.base_client import ...`).

Shared modules are importable as `from shared.xxx import ...` because `server.py` inserts the parent `mcp-servers/` directory into `sys.path` at the top of the file before any other imports:

```python
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)
```

The pytest `conftest.py` does the same, adding both `mcp-servers/` and `mcp-servers/calendar/` to `sys.path` so tests resolve all imports without running the server.

---

## 13. Testing

Tests live in `mcp-servers/calendar/tests/test_server.py`. The test client drives the FastAPI app in-process using `fastapi.testclient.TestClient` — no network calls are made.

**Test doubles (fixtures in `conftest.py`):**

- `mock_google_client` — `MagicMock` with `AsyncMock` `.create_event()` returning a fixed `CalendarEvent`; `.create_events_batch()` returning `([event], [])`; `.list_upcoming()` returning `[event]`
- `mock_outlook_client` — same structure for the Outlook provider
- `mock_clients` — `{"google": mock_google_client, "outlook": mock_outlook_client}`
- `mock_cache` — `AsyncMock` returning `None` (cache miss) by default; individual tests override `.get` for cache-hit paths
- `mock_rate_limiter` — `AsyncMock` returning `True` (allowed) by default; set to `False` for rate-limit tests
- `test_client` — injects all mocks into the `server` module at the global level and wraps with `TestClient`

**Test coverage by area:**

| Area | Tests |
|------|-------|
| Health endpoints (`/livez`, `/readyz`) | 2 |
| JSON-RPC dispatch (parse error, method-not-found, invalid-version) | 3 |
| `create_event` (Google success, Outlook success, missing params, empty token, upstream 401) | 5 |
| `create_weekly_tasks` (Google success, partial failure, Outlook, empty tasks) | 4 |
| `list_upcoming` (Google, Outlook, cache hit, empty token, unconfigured provider) | 5 |
| Rate-limit enforcement | 2 |
| **Total** | **21** |

> Note: `test_create_weekly_tasks_invalid_week_start` is included in the weekly tasks group — it validates that a malformed `week_start` string produces an `INVALID_PARAMS` error rather than a Python exception.

**Running tests:**

```bash
cd mcp-servers/calendar
poetry install
poetry run pytest -v
```

---

## 14. Running Locally

```bash
# 1. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 2. Install dependencies
cd mcp-servers/calendar
poetry install

# 3. Configure environment
cat > .env << 'EOF'
ENVIRONMENT=development
LOG_LEVEL=DEBUG
REDIS_URL=redis://localhost:6379/6

# No provider keys needed here — OAuth tokens are per-request params
# Leave MCP_API_KEY empty to bypass auth in dev
MCP_API_KEY=
EOF

# 4. Run
uvicorn server:app --host 0.0.0.0 --port 3006 --reload
```

**Verify:**
```bash
curl http://localhost:3006/livez
# → {"status":"ok"}

curl http://localhost:3006/readyz
# → {"status":"ok","server_id":"calendar","providers":["google","outlook"]}

# Create a test event (requires a real OAuth token for the provider):
curl -X POST http://localhost:3006/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "create_event",
    "params": {
      "provider": "google",
      "access_token": "YOUR_GOOGLE_OAUTH_TOKEN",
      "title": "Test milestone",
      "start_datetime": "2026-05-11T09:00:00",
      "end_datetime": "2026-05-11T09:30:00",
      "timezone": "Europe/Zurich",
      "reminder_minutes": [60, 10]
    }
  }'
```

**Agents side:** add `MCP_CALENDAR_URL=http://localhost:3006` to `agents/.env`.

---

## 15. Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY mcp-servers/shared /app/mcp-servers/shared
COPY mcp-servers/calendar /app/mcp-servers/calendar

WORKDIR /app/mcp-servers/calendar
RUN pip install poetry && poetry install --no-dev

ENV PYTHONPATH=/app/mcp-servers
EXPOSE 3006
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3006"]
```

`PYTHONPATH=/app/mcp-servers` makes `from shared.xxx import ...` work without the in-process `sys.path` manipulation (which remains as a fallback for direct invocation).

Docker Compose service entry:
```yaml
mcp-calendar:
  build:
    context: .
    dockerfile: mcp-servers/calendar/Dockerfile
  ports: ["3006:3006"]
  environment:
    REDIS_URL: redis://redis:6379/6
    MCP_API_KEY: ${MCP_API_KEY}
    RATE_LIMIT_PER_MINUTE: 30
  depends_on: [redis]
```

No provider credentials are set here — OAuth tokens come from users at runtime, not from environment secrets.

---

## 16. Architecture Decisions

### OAuth tokens are per-request params, not env vars

Every other MCP server stores its upstream credentials as environment variables (API keys, bearer tokens). The Calendar server deliberately does not follow this pattern. Calendar access is personal — there is no single "service account" that can access all users' calendars. Each user has their own Google or Microsoft OAuth token, obtained through the consent flow in the API layer.

Storing credentials as env vars would mean the server could only serve one user, or would require a separate server instance per user (impractical). The per-request token design scales to any number of users and keeps the consent model clean: the server never touches a calendar the user hasn't explicitly authorised.

This also satisfies the CLAUDE.md security requirement: "Require explicit user consent before connecting external accounts (LinkedIn, GitHub, calendar)."

### Both providers always registered

Unlike the Job Board server where API keys are optional and sources are skipped if absent, both Google Calendar and Outlook clients are always registered. There are no server-side credentials to configure. The clients are instantiated once at startup and are ready to handle any user's token at call time.

The cost of registration is negligible (two lightweight objects, no network connections until the first call). The benefit is that `GET /readyz` always reports both providers as available, giving the monitoring layer a clean health signal.

### `create_weekly_tasks` uses partial failure semantics

A batch of 7 weekly tasks should not fail entirely because one event hit a Google API quota error. The `create_events_batch` method uses `asyncio.gather` without `return_exceptions=False`, and individual failures are caught inside the per-event coroutine. Successful events are still returned; only the failing ones appear in `failed_tasks`.

This is especially important at the start of a new week when the agent schedules many events at once — a transient API rate limit on one event should not wipe out the entire week's schedule.

### Outlook reminder limitation is surfaced explicitly

Microsoft Graph supports only a single `reminderMinutesBeforeStart` integer per event, unlike Google which supports up to 5 `overrides`. When a caller provides multiple `reminder_minutes`, the Outlook client silently uses `min(reminder_minutes)` (the closest reminder) and discards the rest.

This is documented in the README, the implementation summary, and in `outlook_client.py` — the limitation is not hidden from future developers. A note in the tool result's `event` object could be added if agents need to surface this to users.

### 5-minute cache for `list_upcoming`, not for write ops

`list_upcoming` reads public-ish data (the user's schedule) that changes only when the user or the roadmap agent writes new events. A 5-minute cache absorbs repeated agent calls within a single coaching conversation without hitting Google/Microsoft API quotas.

Write operations (`create_event`, `create_weekly_tasks`) are intentionally not cached. Caching a write response and returning it for an identical subsequent call would appear to succeed without actually creating the event — a dangerous silent failure that would leave the user's calendar uncorrected.

### Cache key excludes access_token

The `list_upcoming` cache key is derived from `(user_id, provider, time_min, time_max, max_results, calendar_id, timezone)` but explicitly excludes `access_token`. Storing a SHA-256 of the token in a Redis key would be a minor information leak (Redis keys are not secrets) and would also mean the cache never hits when the user's token is refreshed mid-session. The `user_id` header provides per-user isolation instead.

### Rate limit set to 30/min (vs. 60 for other servers)

Calendar operations talk to Google Calendar and Microsoft Graph, which have strict per-user quotas (Google: 1 000 000 queries/day per project; Microsoft: ~10 000 requests/10 minutes per user). Setting a lower rate limit (30/min vs. 60 for social signals) reduces the risk of an agent loop exhausting a user's quota before the agent-level retry logic fires.

### `tzdata` as an explicit dependency

Python's `zoneinfo` module (stdlib since 3.9) requires IANA timezone data, which is available on most Linux systems but is absent on Windows and in minimal Docker containers. Adding `tzdata = ">=2024.1"` to the dependencies ensures timezone resolution works identically in all environments — the server never silently falls back to UTC on a system without `/usr/share/zoneinfo`.
