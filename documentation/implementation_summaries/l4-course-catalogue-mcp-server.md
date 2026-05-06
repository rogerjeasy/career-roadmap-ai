# L4 — Course Catalogue MCP Server

## 1. Context and Purpose

The Course Catalogue MCP Server is the second implemented component of the **L4 MCP Tool Server** layer. It sits between the L3 Specialist Agents and the external learning platforms (Coursera, Udemy, edX, YouTube, O'Reilly), acting as the sole broker for all course and learning resource data.

```
L3 Agents (Learning Resource, Roadmap Generation, Progress Adaptation)
    │
    │  mcp.call("course_catalogue", "search_courses", {...})
    │  JSON-RPC 2.0 over HTTP  ─── X-MCP-API-Key ─── X-Correlation-ID
    ▼
┌──────────────────────────────────────────────────────────┐
│         Course Catalogue MCP Server  :3002               │
│                                                          │
│  POST /   ─── dispatcher ───► search_courses             │
│                           ───► get_course_detail         │
│  GET /livez  GET /readyz  GET /metrics                   │
└─────────────┬────────────────────────────────────────────┘
              │  concurrent async HTTP
    ┌─────────┼──────────┬──────────┬────────────┐
    ▼         ▼          ▼          ▼            ▼
Coursera   Udemy       edX      YouTube      O'Reilly
(RapidAPI) (RapidAPI) (public)  (Data API)  (RapidAPI)
```

Agents never call learning platforms directly. All external API access is permission-scoped, audited, rate-limited, and cacheable at this layer.

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
│   └── base_server.py                   ← MCPApp base (FastAPI + OTel + Prometheus)
│
└── course-catalogue/
    ├── pyproject.toml                   ← Poetry dependencies (port 3002)
    ├── config.py                        ← CourseCatalogueSettings (pydantic-settings)
    ├── models.py                        ← Pydantic data models
    ├── observability.py                 ← Prometheus metrics + get_tracer()
    ├── server.py                        ← entry point, lifespan, dispatcher
    │
    ├── clients/
    │   ├── __init__.py
    │   ├── base_client.py               ← BaseCourseClient (abstract, retry, OTel)
    │   ├── coursera_client.py           ← RapidAPI coursera
    │   ├── udemy_client.py              ← RapidAPI udemy-paid-and-free-courses
    │   ├── youtube_client.py            ← Google YouTube Data API v3
    │   ├── edx_client.py                ← discovery.edx.org public catalog (no key)
    │   └── oreilly_client.py            ← RapidAPI oreilly-learning
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── search_courses.py            ← concurrent search, dedup, rank, cache
    │   └── get_course_detail.py         ← single course detail, 4 h cache
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py                  ← sys.path setup for pytest
        └── test_server.py               ← 14 tests (tools, errors, models)
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
  "method": "search_courses",
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
    "message": "Invalid search_courses parameters",
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
| `-32601` | `METHOD_NOT_FOUND` | Unknown method name or course not found |
| `-32602` | `INVALID_PARAMS` | Pydantic validation failure on params |
| `-32603` | `INTERNAL_ERROR` | Unexpected server exception |
| `-32000` | `RATE_LIMITED` | Per-user sliding window exceeded |
| `-32001` | `UNAUTHORIZED` | Invalid or missing `X-MCP-API-Key` |
| `-32002` | `UPSTREAM_ERROR` | Requested source is not configured |
| `-32003` | `TOOL_TIMEOUT` | Source fetch timed out |
| `-32004` | `CACHE_ERROR` | Redis operation failure |

### Request Headers

| Header | Required | Purpose |
|--------|----------|---------|
| `X-MCP-API-Key` | When `MCP_API_KEY` is set | Server authentication |
| `X-Correlation-ID` | No | Propagated into all logs and OTel spans |
| `X-User-ID` | No | Used as rate-limit key (falls back to `"anonymous"`) |

---

## 4. Tools

### 4.1 `search_courses`

Searches all configured course catalogue sources concurrently, merges results, deduplicates by (title, platform), ranks by relevance, and returns up to `limit` courses.

**Params — `SearchCoursesParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `skill` | `str` (1–200 chars) | required | Skill or topic to search for |
| `level` | `SkillLevel` | `"all"` | `beginner`, `intermediate`, `advanced`, `all` |
| `language` | `str` (2–5 chars) | `"en"` | ISO language code |
| `free_only` | `bool` | `false` | Restrict results to free courses |
| `limit` | `int` (1–50) | `20` | Maximum number of results to return |
| `sources` | `list[CourseSource]` | `[]` | Restrict to specific platforms (empty = all) |

**Result — `SearchCoursesResult`:**
```json
{
  "courses": [ ... ],
  "total_count": 43,
  "sources_queried": ["Coursera", "edX", "YouTube"],
  "fetched_at": "2026-05-06T10:23:11.034Z"
}
```

**Cache TTL:** 1 hour (course catalogues are stable)  
**Rate limit:** 30 calls / minute / user

**Request lifecycle:**

```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Cache lookup  → return cached result if hit
4. Select sources (all configured, or params.sources filter)
5. asyncio.gather(*[client.search(params) for client in sources])
   └─ each client: tenacity retry × 3, OTel span, Prometheus metrics
6. Merge lists → deduplicate by MD5(title+platform) → rank by score
7. Slice to limit → build SearchCoursesResult
8. Write to cache (TTL 3600 s)
9. Emit audit log + metrics → return result
```

**Ranking score formula:**
```
score = rating × 0.3                          # 0–5 star rating, weighted 30%
      + min(log10(num_ratings) × 0.1, 0.5)   # log-scaled popularity, capped 0.5
      + 0.4 if skill_level matches params.level
      + 0.1 if course is free
      + 0.1 if course has certificate
      + 0.05 if duration_hours is known
```

---

### 4.2 `get_course_detail`

Fetches the full detail of a specific course by ID and platform.

**Params — `GetCourseDetailParams`:**

| Field | Type | Description |
|-------|------|-------------|
| `course_id` | `str` | Source-specific course identifier |
| `source` | `CourseSource` | `"Coursera"`, `"Udemy"`, `"edX"`, `"YouTube"`, `"O'Reilly"` |

**Result:** A full `Course` dict (same shape as entries in `search_courses.courses`).

**Cache TTL:** 4 hours (course details are very stable)  
**Rate limit:** 60 calls / minute / user

---

## 5. Data Models

### `Course`

The canonical normalised representation returned by all sources and tools.

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Source-specific ID or SHA-256 hash of title |
| `title` | `str` | Course title as published |
| `platform` | `CourseSource` | Originating platform |
| `instructor` | `str` | Instructor name, channel name, or university |
| `url` | `str` | Link to the course page |
| `description` | `str` | Full or truncated description (max 2000 chars stored; 1000 in API output) |
| `skills` | `list[str]` | Deduplicated, case-normalised skills taught |
| `skill_level` | `SkillLevel` | `beginner`, `intermediate`, `advanced`, `all` |
| `duration_hours` | `float \| None` | Estimated hours to complete |
| `rating` | `float \| None` | 0–5 star rating |
| `num_ratings` | `int \| None` | Number of reviews or view count (YouTube) |
| `price` | `float \| None` | Course price; `None` = free or subscription-based |
| `currency` | `str` | ISO 4217 currency code |
| `free` | `bool` | `True` if freely accessible without subscription |
| `language` | `str` | ISO 639-1 language code |
| `certificate` | `bool` | `True` if a certificate of completion is available |
| `thumbnail_url` | `str \| None` | Course thumbnail or video thumbnail |
| `published_date` | `date \| None` | Original publication date |
| `fetched_at` | `datetime` | UTC timestamp of this fetch |

**Skill deduplication:** The `skills` validator removes case-insensitive duplicates while preserving original capitalisation of the first occurrence.

**`model_dump_api()` output** is the exact dict shape that the `LearningResourceAgent` and `RoadmapGenerationAgent` expect. The `description` field is truncated to 1000 characters in the API output to keep response payloads bounded.

### Enums

**`CourseSource`:**
| Value | Platform |
|-------|----------|
| `"Coursera"` | Coursera |
| `"Udemy"` | Udemy |
| `"edX"` | edX |
| `"YouTube"` | YouTube |
| `"O'Reilly"` | O'Reilly Learning |
| `"unknown"` | Fallback |

**`SkillLevel`:**
| Value | Meaning |
|-------|---------|
| `"beginner"` | No prior experience required |
| `"intermediate"` | Some foundations expected |
| `"advanced"` | Deep prior knowledge expected |
| `"all"` | Mixed or unspecified level |

---

## 6. Data Sources

### Coursera (RapidAPI `coursera.p.rapidapi.com`)

- **Auth:** `COURSERA_API_KEY` → `X-RapidAPI-Key` / `X-RapidAPI-Host` headers
- **Search endpoint:** `GET https://coursera.p.rapidapi.com/` with params `courseName`, `pageSize`, `language`, `difficulty`
- **Detail endpoint:** `GET https://coursera.p.rapidapi.com/{course_id}`
- **Field mapping:** `name` → `title`, `slug` → `id`, `difficultyLevel` → `SkillLevel`, `partners[0].name` → `instructor`, `primaryLanguages[0]` → `language`, `photoUrl` → `thumbnail_url`
- **Rating normalisation:** If `avgRating > 5`, it is assumed to be on a 0–100 scale and divided by 20
- **Free courses:** All Coursera courses are free to audit; `free = True` for all results
- **`get_detail`:** Uses the same host with the slug as path parameter

### Udemy (RapidAPI `udemy-paid-and-free-courses.p.rapidapi.com`)

- **Auth:** `UDEMY_API_KEY` → `X-RapidAPI-Key` / `X-RapidAPI-Host` headers
- **Search endpoint:** `GET /` (all courses) or `GET /free-courses` (when `free_only=True`) with params `search`, `page`, `page_size`, `language`
- **Detail endpoint:** `GET /{course_id}`
- **Level mapping:** `"beginner level"` → `BEGINNER`, `"intermediate level"` → `INTERMEDIATE`, `"expert level"` → `ADVANCED`, `"all levels"` → `ALL`
- **Duration:** `content_length_video` seconds ÷ 3600 → `duration_hours`
- **Price detection:** `is_paid == False` or price string in `{"", "Free", "0", "0.0"}` → `free = True`
- **Instructor:** First entry in `visible_instructors[].display_name`
- **Slug generation:** `_slugify()` lowercases the title and replaces non-alphanumeric runs with `-`
- **Certificate:** Always `True` — every Udemy course offers a certificate of completion

### YouTube (Google YouTube Data API v3)

- **Auth:** `YOUTUBE_API_KEY` → `key` query parameter on all calls
- **Two-step fetch:**
  1. `GET /youtube/v3/search` — find up to 25 video IDs matching `{skill} tutorial course`; filters: `type=video`, `videoDuration=long`, `safeSearch=strict`
  2. `GET /youtube/v3/videos?part=contentDetails,statistics,snippet` — fetch duration and view/like counts for all returned IDs in a single call
- **Duration parsing:** `PT1H23M45S` ISO 8601 format → `_parse_iso8601_duration()` → hours as float
- **Rating proxy:** `(likeCount / viewCount) × 4 + 1` — scales like ratio into a 1–5 star range
- **Popularity proxy:** `viewCount` stored as `num_ratings`
- **Free / certificate:** Always `free=True`, always `certificate=False` (YouTube videos have no certificate)
- **Level inference:** Always `SkillLevel.ALL` — YouTube does not tag level

### edX (public discovery catalog — no API key required)

- **Endpoint:** `GET https://discovery.edx.org/api/v1/search/all/` with params `q`, `content_type=course`, `page_size`, `level_type`, `language`
- **Detail endpoint:** `GET https://discovery.edx.org/api/v1/courses/{key}/`
- **Level mapping:** `"introductory"` / `"beginner"` → `BEGINNER`, `"intermediate"` → `INTERMEDIATE`, `"advanced"` → `ADVANCED`
- **Instructor:** First entry in `owners[].name` (the university or organisation)
- **Skills proxy:** `subjects[].name` — edX subjects (e.g., "Computer Science", "Data Analysis") are used as the skills list
- **Free courses:** All edX courses are free to audit; `free=True` for all results
- **Certificate detection:** `entitlements` list is checked for an entry with `mode == "verified"` — if present, `certificate=True`
- **Always registered:** edX requires no API key and is always active, ensuring at least one source is always available

### O'Reilly Learning (RapidAPI `oreilly-learning.p.rapidapi.com`)

- **Auth:** `OREILLY_API_KEY` → `X-RapidAPI-Key` / `X-RapidAPI-Host` headers
- **Search endpoint:** `GET /search` with params `query`, `formats=video,learning_path`, `page_size`, `page`, `language`, `level`
- **Detail endpoint:** `GET /content/{course_id}`
- **Topics → skills:** `topics[].name` or `topics[].slug` extracted as the skills list
- **Duration:** `duration_seconds ÷ 3600` → `duration_hours` when `duration_seconds` key is present; `minutes_of_content ÷ 60` otherwise
- **Subscription model:** O'Reilly is always `free=False` and `certificate=False` — it is a subscription library
- **`free_only` skip:** When `free_only=True`, O'Reilly results are excluded entirely at the tool level before the client is called
- **Authors:** First entry in `authors[].name` or `authors[].full_name`

---

## 7. Shared Modules

All shared modules are identical to those used by the Job Board MCP Server. See `l4-job-board-mcp-server.md § 7. Shared Modules` for the full reference. A brief recap:

### `shared/error_handler.py`

`JsonRpcErrorCode` enum + `make_success_response()` / `make_error_response()` builders.  
`JsonRpcError` is raised by tool handlers to produce a well-formed error without triggering the generic 500 handler.

### `shared/auth.py`

`verify_api_key()` compares `X-MCP-API-Key` against `MCP_API_KEY` using `hmac.compare_digest`. Bypassed when `MCP_API_KEY` is empty.

### `shared/cache.py`

`ResponseCache` wraps `redis.asyncio`. Cache keys:
```
mcp:cache:{tool}:{sha256(json({tool, params}))[:16]}
```
All Redis failures are caught and logged; the caller receives `None` and proceeds without cache.

### `shared/rate_limiter.py`

Sliding-window limiter per `(user_id, tool)`. Fails open when Redis is unavailable.

---

## 8. Client Architecture

### `BaseCourseClient`

All five clients inherit from this abstract class. It provides:

- **Async context manager:** creates and closes `httpx.AsyncClient` with shared timeout and browser-like headers
- **`search(params)` / `get_detail(id)`:** public methods that wrap the subclass hooks with error handling, OTel spans, and Prometheus recording
- **`_get()` / `_post()`:** tenacity-decorated HTTP helpers that retry on `TimeoutException` and `TransportError` with exponential back-off (3 attempts, 0.5–4 s window)
- **Fail-safe:** all public methods return `[]` or `None` on any exception — a broken source never propagates an error to the dispatcher

```python
async with CourseraClient(api_key=key) as client:
    courses = await client.search(params, correlation_id=cid)
    # Returns [] if Coursera API is down, times out, or returns bad data
```

### Client Lifecycle

Clients are instantiated once at startup in `_build_clients()` and held in the module-level `_clients` dict. The `httpx.AsyncClient` is created lazily on the first `search()` call via `__aenter__`. HTTP connections are reused across requests within the same process.

### Source Registration Logic

```python
# server.py: _build_clients()

if settings.coursera_api_key:   → register CourseraClient
if settings.udemy_api_key:      → register UdemyClient
if settings.youtube_api_key:    → register YouTubeClient
if settings.oreilly_api_key:    → register OReillyClient

# Always registered (no key needed):
EdxClient(discovery_base_url=settings.edx_discovery_url)
```

The server logs a warning but does not crash if no keyed sources are configured — edX always provides a functional baseline.

---

## 9. Observability

### Prometheus Metrics

All metrics are prefixed `mcp_course_catalogue_`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_course_catalogue_fetch_total` | Counter | `source`, `status` | Upstream fetch calls by source and outcome |
| `mcp_course_catalogue_fetch_duration_seconds` | Histogram | `source` | Fetch latency per source |
| `mcp_course_catalogue_fetch_results_count` | Histogram | `source` | Courses returned per source fetch |
| `mcp_course_catalogue_cache_hits_total` | Counter | `tool` | Cache hits by tool |
| `mcp_course_catalogue_cache_misses_total` | Counter | `tool` | Cache misses by tool |
| `mcp_course_catalogue_rate_limit_hit_total` | Counter | `tool` | Rate-limited requests by tool |
| `mcp_course_catalogue_tool_call_total` | Counter | `method`, `status` | Tool invocations by method and outcome |
| `mcp_course_catalogue_tool_call_duration_seconds` | Histogram | `method` | End-to-end tool call latency |
| `mcp_course_catalogue_courses_with_rating_total` | Counter | `source` | Courses that included rating data |
| `mcp_course_catalogue_courses_with_duration_total` | Counter | `source` | Courses that included duration data |
| `mcp_course_catalogue_free_courses_total` | Counter | `source` | Free courses returned by source |
| `mcp_course_catalogue_audit_log_total` | Counter | `tool` | Audit log events emitted |

Status labels for `fetch_total`: `success`, `error`, `timeout`, `rate_limited`  
Status labels for `tool_call_total`: `ok`, `cache_hit`, `rpc_error`, `error`, `rate_limited`

### OpenTelemetry Spans

| Span Name | Created by | Attributes |
|-----------|------------|------------|
| `tool.search_courses` | `search_courses.py` | `user_id`, `correlation_id`, `skill`, `level`, `result_count` |
| `tool.get_course_detail` | `get_course_detail.py` | `user_id`, `correlation_id`, `course_id`, `source` |
| `course_catalogue.{source}.search` | `base_client.py` | `source`, `skill`, `level`, `result_count`, `latency_ms` |

OTLP export is enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. In development, spans are printed to stdout via `ConsoleSpanExporter`.

### Structured Logging

All logs use `structlog` with keyword arguments. Key events:

```python
logger.info("course_catalogue.clients_registered", sources=["Coursera", "edX", "YouTube"])
logger.info("search_courses.completed", skill=..., level=..., total_found=43, returned=20, ...)
logger.warning("course_catalogue.search_failed", source="Coursera", error="...")
logger.info("search_courses.cache_hit", skill=..., level=..., correlation_id=...)
logger.info("get_course_detail.completed", course_id=..., source=..., latency_ms=...)
```

Format: JSON in production, coloured console in dev.

### Health Endpoints

```
GET /livez   → 200 {"status": "ok"}
GET /readyz  → 200 {"status": "ok", "server_id": "course_catalogue", "sources": [...]}
GET /metrics → 200 (Prometheus text format)
```

---

## 10. Configuration Reference

All values are loaded from environment variables via `CourseCatalogueSettings` (pydantic-settings). A `.env` file is supported in development.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENVIRONMENT` | `development` | No | `development`, `staging`, `production` |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HOST` | `0.0.0.0` | No | Bind address for uvicorn |
| `PORT` | `3002` | No | Listen port |
| `MCP_API_KEY` | `""` | No | Shared secret for `X-MCP-API-Key` auth (empty = bypass) |
| `REDIS_URL` | `redis://localhost:6379/2` | No | Redis DSN (DB 2, separate from job-board's DB 1) |
| `CACHE_TTL_SECONDS` | `3600` | No | Default cache TTL (1 hour — courses are stable) |
| `RATE_LIMIT_PER_MINUTE` | `30` | No | Max requests per user per minute |
| `COURSERA_API_KEY` | — | No | RapidAPI key for Coursera |
| `COURSERA_API_HOST` | `coursera.p.rapidapi.com` | No | RapidAPI host override |
| `UDEMY_API_KEY` | — | No | RapidAPI key for Udemy |
| `UDEMY_API_HOST` | `udemy-paid-and-free-courses.p.rapidapi.com` | No | RapidAPI host override |
| `YOUTUBE_API_KEY` | — | No | Google Cloud API key with YouTube Data API v3 enabled |
| `YOUTUBE_BASE_URL` | `https://www.googleapis.com/youtube/v3` | No | YouTube API base URL override |
| `OREILLY_API_KEY` | — | No | RapidAPI key for O'Reilly Learning |
| `OREILLY_API_HOST` | `oreilly-learning.p.rapidapi.com` | No | RapidAPI host override |
| `EDX_DISCOVERY_URL` | `https://discovery.edx.org` | No | edX discovery base URL |
| `HTTP_TIMEOUT_SECONDS` | `15.0` | No | Per-source request timeout |
| `HTTP_MAX_RETRIES` | `3` | No | Tenacity retry attempts |
| `DEFAULT_RESULTS_PER_SOURCE` | `10` | No | Default limit per source fetch |
| `MAX_TOTAL_RESULTS` | `50` | No | Hard cap on merged results before ranking |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | No | OTLP gRPC endpoint for trace export |

The Redis DB index is `2` to avoid colliding with the job-board server (`1`) on the same Redis instance.

---

## 11. Agent Integration

The agents layer connects via `HttpMCPClient`. Three agents use this server:

### Learning Resource Agent

Primary consumer. Calls `search_courses` for each skill gap identified in the user's career plan, requesting courses at the appropriate level.

```python
raw = await mcp_client.call(
    "course_catalogue",
    "search_courses",
    {
        "skill": "LangGraph",
        "level": "intermediate",
        "limit": 10,
        "free_only": False,
    },
    correlation_id=correlation_id,
)
# raw["courses"] → list of Course dicts
```

Configured via `MCP_COURSE_CATALOGUE_URL` in the agents `.env`.

### Roadmap Generation Agent

Calls `search_courses` to annotate each week of the generated roadmap with concrete learning resources. Passes `free_only=True` when the user has indicated budget constraints.

### Progress Adaptation Agent

Calls `get_course_detail` to fetch the full description and duration of a course when adapting the roadmap based on the user's reported completion progress. Uses duration data to recalibrate weekly time estimates.

### Stub fallback

When `MCP_COURSE_CATALOGUE_URL` is not set, agents use `StubMCPClient` which returns realistic mock courses without any network calls.

---

## 12. Path Resolution

The `course-catalogue/` directory name contains a dash, making it non-importable as a Python package. Imports within the server use flat module names (e.g., `from models import Course`, `from clients.base_client import ...`).

`server.py` inserts the parent `mcp-servers/` directory into `sys.path` at the top of the file:

```python
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)
```

The pytest `conftest.py` does the same, adding both `mcp-servers/` and `mcp-servers/course-catalogue/` to `sys.path`.

---

## 13. Testing

Tests live in `mcp-servers/course-catalogue/tests/test_server.py`. The test client drives the FastAPI app in-process using `fastapi.testclient.TestClient` — no network calls are made.

**Test doubles:**

- `_StubClient` — implements `search()` and `get_detail()` returning controlled `Course` objects
- `stub_cache` — `AsyncMock` returning `None` (cache miss) by default; individual tests override `stub_cache.get` for cache-hit paths
- `stub_rate_limiter` — `AsyncMock` allowing all requests by default; set `return_value=False` to test rate-limit paths

**Test coverage by area:**

| Area | Tests |
|------|-------|
| Health endpoints (`/livez`, `/readyz`, `/metrics`) | 3 |
| JSON-RPC dispatch (parse error, method-not-found, invalid-request) | 3 |
| `search_courses` (valid, invalid params, field shape, cache hit, rate limited, free-only filter) | 6 |
| `get_course_detail` (found, not found, invalid params, unconfigured source) | 4 |
| Model unit tests (`Course` dedup, `model_dump_api` shape, description truncation) | 3 |
| **Total** | **19** |

**Running tests:**

```bash
cd mcp-servers/course-catalogue
poetry install
poetry run pytest -v
```

---

## 14. Running Locally

```bash
# 1. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 2. Install dependencies
cd mcp-servers/course-catalogue
poetry install

# 3. Configure environment
cat > .env << 'EOF'
ENVIRONMENT=development
LOG_LEVEL=DEBUG
REDIS_URL=redis://localhost:6379/2

# Optional — server works without these (edX always active)
COURSERA_API_KEY=your-rapidapi-key
UDEMY_API_KEY=your-rapidapi-key
YOUTUBE_API_KEY=your-google-cloud-key
OREILLY_API_KEY=your-rapidapi-key

# Optional — leave empty to disable auth in dev
MCP_API_KEY=
EOF

# 4. Run
uvicorn server:app --host 0.0.0.0 --port 3002 --reload
```

**Verify:**
```bash
curl http://localhost:3002/livez
# → {"status":"ok"}

curl -X POST http://localhost:3002/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"search_courses","params":{"skill":"Python","level":"beginner","limit":5}}'
```

**Agents side:** add `MCP_COURSE_CATALOGUE_URL=http://localhost:3002` to `agents/.env`.

---

## 15. Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY mcp-servers/shared /app/mcp-servers/shared
COPY mcp-servers/course-catalogue /app/mcp-servers/course-catalogue

WORKDIR /app/mcp-servers/course-catalogue
RUN pip install poetry && poetry install --no-dev

ENV PYTHONPATH=/app/mcp-servers
EXPOSE 3002
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3002"]
```

`PYTHONPATH=/app/mcp-servers` makes `from shared.xxx import ...` work without the in-process `sys.path` manipulation.

Docker Compose service entry:
```yaml
mcp-course-catalogue:
  build:
    context: .
    dockerfile: mcp-servers/course-catalogue/Dockerfile
  ports: ["3002:3002"]
  environment:
    REDIS_URL: redis://redis:6379/2
    COURSERA_API_KEY: ${COURSERA_API_KEY}
    UDEMY_API_KEY: ${UDEMY_API_KEY}
    YOUTUBE_API_KEY: ${YOUTUBE_API_KEY}
    OREILLY_API_KEY: ${OREILLY_API_KEY}
    MCP_API_KEY: ${MCP_API_KEY}
  depends_on: [redis]
```

---

## 16. Architecture Decisions

### edX always registered

edX exposes a public catalog API requiring no API key. This ensures the server is never completely dark even in a dev environment with no credentials configured. Free, high-quality courses are always available to agents regardless of API key provisioning.

### Cache TTL is 1 hour, not 5 minutes

Course catalogues change slowly compared to job boards — a new course appears on Coursera or Udemy perhaps weekly, not hourly. A 1-hour TTL dramatically reduces upstream API calls and RapidAPI quota consumption while keeping the data fresh enough for career coaching purposes.

### YouTube two-step fetch

The YouTube search API returns video metadata but not duration or statistics — those require a second `videos` call. Rather than making N individual video detail calls, all IDs from the search result are batched into a single `videos?id=a,b,c,...` request. This keeps the two-step fetch at a fixed cost of 2 API calls regardless of result count.

### Rating proxy for YouTube

YouTube does not expose a 5-star rating. The like-to-view ratio is used as a proxy: `1 + (likes/views) × 4`. This produces a reasonable 1–5 range where viral educational content scores highly. View count is stored as `num_ratings` to drive the log-scaled popularity component of the ranking formula.

### `free_only` filtering at tool level for O'Reilly

O'Reilly is a subscription service — no individual course is free. Rather than calling the O'Reilly API and then filtering all results out, the tool skips the O'Reilly client entirely when `free_only=True`. This avoids a wasted API call and quota consumption.

### Sources fail independently

Each client's `search()` method catches all exceptions and returns `[]`. `asyncio.gather(*tasks, return_exceptions=True)` ensures that a YouTube quota exhaustion does not cancel the Coursera or edX fetches. The merged result is always the best available subset.

### Rate limit is 30/min, not 60/min

Course search is more expensive than job search: up to 5 upstream API calls per request (including YouTube's two-step fetch), each consuming external API quota. A tighter rate limit of 30 req/min/user protects external quota from agent hot loops while still supporting normal usage patterns.
