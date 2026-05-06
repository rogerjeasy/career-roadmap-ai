# L4 — Job Board MCP Server

## 1. Context and Purpose

The Job Board MCP Server is the first implemented component of the **L4 MCP Tool Server** layer. It sits between the L3 Specialist Agents and the external job platforms (LinkedIn, Indeed, Glassdoor, Swiss portals), acting as the sole broker for all live job market data.

```
L3 Agents (Market Intelligence, Opportunity Matching)
    │
    │  mcp.call("job_board", "search_jobs", {...})
    │  JSON-RPC 2.0 over HTTP  ─── X-MCP-API-Key ─── X-Correlation-ID
    ▼
┌─────────────────────────────────────────────────────┐
│           Job Board MCP Server  :3001               │
│                                                     │
│  POST /   ─── dispatcher ───► search_jobs           │
│                           ───► get_job_detail        │
│                           ───► get_trending_roles    │
│  GET /livez  GET /readyz  GET /metrics               │
└─────────────┬───────────────────────────────────────┘
              │  concurrent async HTTP
    ┌─────────┼──────────────┬────────────────┐
    ▼         ▼              ▼                ▼
LinkedIn   Indeed        Glassdoor       jobs.ch
(RapidAPI) (RapidAPI)   (RapidAPI)     jobup.ch
```

Agents never call job platforms directly. All external API access is permission-scoped, audited, rate-limited, and cacheable at this layer.

---

## 2. File Structure

```
mcp-servers/
├── shared/                         ← reused by all 7 MCP servers
│   ├── __init__.py
│   ├── auth.py                     ← X-MCP-API-Key HMAC validation
│   ├── cache.py                    ← Redis response cache (SHA-256 keyed)
│   ├── rate_limiter.py             ← sliding-window per-(user, tool) limiter
│   ├── error_handler.py            ← JSON-RPC 2.0 error codes + builders
│   └── base_server.py              ← MCPApp base (FastAPI + OTel + Prometheus)
│
└── job-board/
    ├── pyproject.toml              ← Poetry dependencies
    ├── config.py                   ← JobBoardSettings (pydantic-settings)
    ├── models.py                   ← Pydantic data models
    ├── observability.py            ← Prometheus metrics + get_tracer()
    ├── server.py                   ← entry point, lifespan, dispatcher
    │
    ├── clients/
    │   ├── __init__.py
    │   ├── base_client.py          ← BaseJobBoardClient (abstract, retry, OTel)
    │   ├── linkedin_client.py      ← RapidAPI linkedin-jobs-search
    │   ├── indeed_client.py        ← RapidAPI indeed12
    │   ├── glassdoor_client.py     ← RapidAPI glassdoor
    │   └── swiss_jobs_client.py    ← jobs.ch + jobup.ch (no key required)
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── search_jobs.py          ← concurrent search, dedup, rank, cache
    │   ├── get_job_detail.py       ← single posting detail, 1 h cache
    │   └── get_trending_roles.py   ← cross-source trending aggregation
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py             ← sys.path setup for pytest
        └── test_server.py          ← 20 tests (tools, errors, models)
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
  "method": "search_jobs",
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
    "message": "Invalid search_jobs parameters",
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
| `-32601` | `METHOD_NOT_FOUND` | Unknown method name or job not found |
| `-32602` | `INVALID_PARAMS` | Pydantic validation failure on params |
| `-32603` | `INTERNAL_ERROR` | Unexpected server exception |
| `-32000` | `RATE_LIMITED` | Per-user sliding window exceeded |
| `-32001` | `UNAUTHORIZED` | Invalid or missing `X-MCP-API-Key` |
| `-32002` | `UPSTREAM_ERROR` | All configured sources are unconfigured |
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

### 4.1 `search_jobs`

Searches all configured job board sources concurrently, merges results, deduplicates by (title, company), ranks by relevance, and returns up to `limit` postings.

**Params — `SearchJobsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | `str` (1–200 chars) | required | Job title / role to search |
| `country` | `str` (ISO 3166 alpha-2) | `"CH"` | Target country |
| `location` | `str \| None` | `None` | City or region override |
| `remote` | `bool \| None` | `None` | Filter for remote jobs |
| `skills` | `list[str]` | `[]` | Used to boost query and ranking |
| `experience_level` | `ExperienceLevel \| None` | `None` | `entry`, `mid`, `senior`, `lead`, `executive` |
| `employment_type` | `EmploymentType \| None` | `None` | `full_time`, `part_time`, `contract`, `internship`, `freelance` |
| `salary_min` | `int \| None` | `None` | Minimum annual salary filter |
| `limit` | `int` (1–50) | `20` | Maximum number of results to return |
| `sources` | `list[JobSource]` | `[]` | Restrict to specific sources (empty = all) |

**Result — `SearchJobsResult`:**
```json
{
  "postings": [ ... ],
  "total_count": 87,
  "sources_queried": ["LinkedIn", "Indeed", "jobs.ch"],
  "fetched_at": "2026-05-06T10:23:11.034Z"
}
```

**Cache TTL:** 5 minutes  
**Rate limit:** 60 calls / minute / user

**Request lifecycle:**

```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Cache lookup  → return cached result if hit
4. Select sources (all configured, or params.sources filter)
5. asyncio.gather(*[client.search(params) for client in sources])
   └─ each client: tenacity retry × 3, OTel span, Prometheus metrics
6. Merge lists → deduplicate by SHA-256(title+company) → rank by score
7. Slice to limit → build SearchJobsResult
8. Write to cache (TTL 300 s)
9. Emit audit log + metrics → return result
```

**Ranking score formula:**
```
score = recency_bonus(days_old)   # max 1.0, decays over 30 days
      + 0.3 if salary data present
      + 0.2 × |params.skills ∩ posting.required_skills|
      + 0.2 if remote match
```

---

### 4.2 `get_job_detail`

Fetches the full detail of a specific job posting by ID and source platform.

**Params — `GetJobDetailParams`:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | Source-specific posting identifier |
| `source` | `JobSource` | `"LinkedIn"`, `"Indeed"`, `"Glassdoor"`, `"jobs.ch"`, `"jobup.ch"` |

**Result:** A full `JobPosting` dict (same shape as entries in `search_jobs.postings`).

**Cache TTL:** 1 hour (job details are stable once posted)  
**Rate limit:** 120 calls / minute / user

---

### 4.3 `get_trending_roles`

Aggregates trending role data from all configured sources, merges roles with the same title, and returns a ranked list with posting counts, week-over-week growth, and top required skills.

**Params — `GetTrendingRolesParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `country` | `str` (alpha-2) | `"CH"` | Market to analyse |
| `category` | `str \| None` | `None` | Optional keyword filter on role title |
| `limit` | `int` (1–25) | `10` | Max roles to return |

**Result:**
```json
{
  "trending_roles": [
    {
      "title": "Software Engineer",
      "posting_count": 820,
      "growth_percent": 12.5,
      "top_skills": ["Python", "Docker", "Kubernetes", "AWS", "FastAPI"],
      "median_salary": 115000,
      "currency": "CHF",
      "country": "CH",
      "sources": ["LinkedIn", "jobs.ch"]
    }
  ],
  "country": "CH",
  "fetched_at": "2026-05-06T10:23:11.034Z",
  "sources": ["LinkedIn", "Indeed", "jobs.ch"]
}
```

**Merge logic:** roles with the same normalised title (case-insensitive) are merged — posting counts are summed, growth is averaged, skills are union-ranked by frequency across sources.

**Cache TTL:** 1 hour  
**Rate limit:** 30 calls / minute / user

---

## 5. Data Models

### `JobPosting`

The canonical normalised representation returned by all sources and tools.

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Source-specific ID or SHA-256 hash of (title, company) |
| `title` | `str` | Job title as posted |
| `company` | `str` | Employer name |
| `location` | `str` | City / region string |
| `country` | `str` | Inferred ISO alpha-2 code |
| `remote` | `bool` | True if remote / home office |
| `employment_type` | `EmploymentType` | `full_time`, `part_time`, `contract`, `internship`, `freelance`, `unknown` |
| `experience_level` | `ExperienceLevel` | `entry`, `mid`, `senior`, `lead`, `executive`, `unknown` |
| `description` | `str` | Full or truncated description (max 2000 chars) |
| `required_skills` | `list[str]` | Deduplicated, case-normalised skill list |
| `nice_to_have_skills` | `list[str]` | Deduplicated nice-to-have skills |
| `salary_min` | `int \| None` | Annual minimum in local currency |
| `salary_max` | `int \| None` | Annual maximum in local currency |
| `currency` | `str` | ISO 4217 currency code (`CHF`, `EUR`, `USD`, ...) |
| `source` | `JobSource` | Originating platform |
| `source_url` | `str \| None` | Link to the original posting |
| `apply_url` | `str \| None` | Direct application URL if available |
| `posted_date` | `date \| None` | ISO date of original posting |
| `fetched_at` | `datetime` | UTC timestamp of this fetch |

**`model_dump_api()` output** is the exact dict shape that `JobBoardFetcher._parse_postings()` in the agents layer expects. The field `url` (not `source_url`) is used in the agent-facing output for backward compatibility.

### `TrendingRole`

| Field | Type | Notes |
|-------|------|-------|
| `title` | `str` | Role title |
| `posting_count` | `int` | Number of live postings found |
| `growth_percent` | `float` | Week-over-week growth estimate |
| `top_skills` | `list[str]` | Top required skills by frequency |
| `median_salary` | `int \| None` | Median annual salary if available |
| `currency` | `str` | ISO 4217 code |
| `country` | `str` | ISO alpha-2 market |
| `sources` | `list[JobSource]` | Sources that contributed data |

---

## 6. Data Sources

### LinkedIn (RapidAPI `linkedin-jobs-search`)

- **Auth:** `LINKEDIN_API_KEY` + `LINKEDIN_API_HOST` → `X-RapidAPI-Key` / `X-RapidAPI-Host` headers
- **Endpoint:** `GET https://linkedin-jobs-search.p.rapidapi.com/`
- **Params mapped:** `keywords`, `locationId` (LinkedIn URN), `datePosted`, `workplaceType`, `experienceLevel`, `jobType`
- **Country → LinkedIn ID:** `CH → urn:li:country:ch`, `DE → urn:li:country:de`, etc.
- **Skill extraction:** Uses structured `skills` field when available; falls back to heuristic text scan
- **`get_trending_roles`:** LinkedIn doesn't expose trending data via this API, so a ranked static list of common tech roles is returned

### Indeed (RapidAPI `indeed12`)

- **Auth:** `INDEED_API_KEY` + `INDEED_API_HOST`
- **Endpoint:** `GET https://indeed12.p.rapidapi.com/jobs/search`
- **Detail endpoint:** `GET https://indeed12.p.rapidapi.com/job`
- **Country domain:** `CH → ch`, `DE → de`, `US → www`, `GB → uk`, etc.
- **Skill extraction:** Heuristic scan of 40+ known tech skills against description text
- **Salary:** Parsed from nested `salary.{min,max,currency}` structure

### Glassdoor (RapidAPI `glassdoor`)

- **Auth:** `GLASSDOOR_API_KEY` + `GLASSDOOR_API_HOST`
- **Endpoint:** `GET https://glassdoor.p.rapidapi.com/jobs/search`
- **Detail endpoint:** `GET https://glassdoor.p.rapidapi.com/jobs/detail`
- **Response structure:** Nested under `data.jobListings[].jobview.job`
- **Salary data:** Glassdoor's salary benchmarks are embedded in the job view; particularly valuable for `get_trending_roles` median salary data

### jobs.ch + jobup.ch (No API key)

- **jobs.ch endpoint:** `GET https://www.jobs.ch/api/v1/public/search/`
- **jobup.ch endpoint:** `GET https://www.jobup.ch/api/search/jobs/`
- **Both fetched concurrently** within `SwissJobsClient._search()` via `asyncio.gather`
- **Deduplication:** After both results are merged, duplicates are removed by MD5(title+company)
- **Swiss-specific:** Employment type inferred from `workload` percentage (≥80% → full_time)
- **Always active:** Registered regardless of API key configuration

---

## 7. Shared Modules

### `shared/error_handler.py`

Defines the `JsonRpcErrorCode` enum and two builder functions:

```python
make_success_response(request_id, result)  # → {"jsonrpc":"2.0","id":...,"result":...}
make_error_response(request_id, code, message, data=None)  # → {"jsonrpc":"2.0","id":...,"error":{...}}
```

`JsonRpcError` is a standard Python exception that tool handlers raise to signal a well-formed error without triggering the generic 500 handler.

### `shared/auth.py`

`verify_api_key()` is a FastAPI dependency injected into the `POST /` route. It reads `X-MCP-API-Key` from the request header and compares it with `MCP_API_KEY` using `hmac.compare_digest` (constant-time comparison, prevents timing attacks). When `MCP_API_KEY` is not set in the environment, the check is bypassed entirely — this is the intended dev workflow.

### `shared/cache.py`

`ResponseCache` wraps `redis.asyncio`. Cache keys are derived as:

```
mcp:cache:{tool}:{sha256(json({tool, params}))[:16]}
```

Sorting `params` by key before hashing ensures cache hits regardless of dict ordering. All Redis failures are caught and logged; the caller receives `None` and proceeds without cache. TTL defaults to `CACHE_TTL_SECONDS` (300 s) but each tool can override it per call.

### `shared/rate_limiter.py`

`RateLimiter` implements a Redis sorted-set sliding window:

```
ZREMRANGEBYSCORE key -inf (now - window_seconds)  # expire old entries
ZADD key now now                                   # record this request
ZCARD key                                          # count within window
EXPIRE key (window_seconds + 1)                    # auto-cleanup
```

Limit is checked per `(user_id, tool)` pair. When Redis is unavailable, the limiter fails open (returns `True`) so that a cache outage does not block agents.

### `shared/base_server.py`

`MCPApp` is a thin wrapper around FastAPI. It pre-registers `/livez`, `/readyz`, and `/metrics` endpoints, sets up structlog and OTel in the lifespan, and owns two shared Prometheus metrics:

- `mcp_{server_id}_rpc_requests_total` — labelled by `method`, `status`
- `mcp_{server_id}_rpc_duration_seconds` — labelled by `method`

The job-board `server.py` does not use `MCPApp` directly — it builds its own FastAPI app for finer control over lifespan and client injection — but it imports `_configure_logging` and `_configure_tracing` from this module.

---

## 8. Client Architecture

### `BaseJobBoardClient`

All four clients inherit from this abstract class. It provides:

- **Async context manager:** creates and closes `httpx.AsyncClient` with shared timeout and browser-like headers
- **`search(params)` / `get_detail(id)` / `get_trending_roles(country, limit)`:** public methods that wrap the subclass hooks with error handling, OTel spans, and Prometheus recording
- **`_get()` / `_post()`:** tenacity-decorated HTTP helpers that retry on `TimeoutException` and `TransportError` with exponential back-off (3 attempts, 0.5–4 s window)
- **Fail-safe:** all public methods return `[]` or `None` on any exception — a broken source never propagates an error to the dispatcher

```python
async with LinkedInClient(api_key=key) as client:
    postings = await client.search(params, correlation_id=cid)
    # Returns [] if LinkedIn API is down, times out, or returns bad data
```

### Client Lifecycle

Clients are **not** used as context managers in the server — they are instantiated once at startup in `_build_clients()` and held in the module-level `_clients` dict. The `httpx.AsyncClient` is created lazily on the first `search()` call via `__aenter__`. This means all HTTP connections are reused across requests within the same process.

---

## 9. Observability

### Prometheus Metrics

All metrics are prefixed `mcp_job_board_`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_job_board_fetch_total` | Counter | `source`, `status` | Upstream fetch calls by source and outcome |
| `mcp_job_board_fetch_duration_seconds` | Histogram | `source` | Fetch latency per source |
| `mcp_job_board_fetch_results_count` | Histogram | `source` | Postings returned per fetch |
| `mcp_job_board_cache_hits_total` | Counter | `tool` | Cache hits by tool |
| `mcp_job_board_cache_misses_total` | Counter | `tool` | Cache misses by tool |
| `mcp_job_board_rate_limit_hit_total` | Counter | `tool` | Rate-limited requests by tool |
| `mcp_job_board_tool_call_total` | Counter | `method`, `status` | Tool invocations by method and outcome |
| `mcp_job_board_tool_call_duration_seconds` | Histogram | `method` | End-to-end tool call latency |
| `mcp_job_board_postings_with_salary_total` | Counter | `source` | Postings that included salary data |
| `mcp_job_board_postings_skills_count` | Histogram | — | Required skills count per posting |
| `mcp_job_board_audit_log_total` | Counter | `tool` | Audit log events emitted |

Status labels for `fetch_total`: `success`, `error`, `timeout`, `rate_limited`  
Status labels for `tool_call_total`: `ok`, `cache_hit`, `rpc_error`, `error`

### OpenTelemetry Spans

| Span Name | Created by | Attributes |
|-----------|------------|------------|
| `tool.search_jobs` | `search_jobs.py` | `user_id`, `correlation_id`, `role`, `country`, `result_count` |
| `tool.get_job_detail` | `get_job_detail.py` | `user_id`, `correlation_id`, `job_id`, `source` |
| `tool.get_trending_roles` | `get_trending_roles.py` | `user_id`, `correlation_id`, `country` |
| `job_board.{source}.search` | `base_client.py` | `source`, `role`, `country`, `result_count`, `latency_ms` |

OTLP export is enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. In development, spans are printed to stdout via `ConsoleSpanExporter`.

### Structured Logging

All logs use `structlog` with keyword arguments. Key events:

```python
logger.info("job_board.clients_registered", sources=["LinkedIn", "jobs.ch"])
logger.info("search_jobs.completed", role=..., country=..., total_found=87, returned=20, ...)
logger.warning("job_board.search_failed", source="LinkedIn", error="...")
logger.info("search_jobs.cache_hit", role=..., country=..., correlation_id=...)
```

Format: JSON in production (`ENVIRONMENT != "development"`), coloured console in dev.

### Health Endpoints

```
GET /livez   → 200 {"status": "ok"}
GET /readyz  → 200 {"status": "ok", "server_id": "job_board", "sources": [...]}
GET /metrics → 200 (Prometheus text format)
```

---

## 10. Configuration Reference

All values are loaded from environment variables via `JobBoardSettings` (pydantic-settings). A `.env` file is supported in development.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENVIRONMENT` | `development` | No | `development`, `staging`, `production` |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HOST` | `0.0.0.0` | No | Bind address for uvicorn |
| `PORT` | `3001` | No | Listen port |
| `MCP_API_KEY` | `""` | No | Shared secret for `X-MCP-API-Key` auth (empty = bypass) |
| `REDIS_URL` | `redis://localhost:6379/1` | No | Redis DSN for cache and rate limiter |
| `CACHE_TTL_SECONDS` | `300` | No | Default cache TTL in seconds |
| `RATE_LIMIT_PER_MINUTE` | `60` | No | Max requests per user per minute |
| `LINKEDIN_API_KEY` | — | No | RapidAPI key for LinkedIn Jobs |
| `LINKEDIN_API_HOST` | `linkedin-jobs-search.p.rapidapi.com` | No | RapidAPI host override |
| `INDEED_API_KEY` | — | No | RapidAPI key for Indeed |
| `INDEED_API_HOST` | `indeed12.p.rapidapi.com` | No | RapidAPI host override |
| `GLASSDOOR_API_KEY` | — | No | RapidAPI key for Glassdoor |
| `GLASSDOOR_API_HOST` | `glassdoor.p.rapidapi.com` | No | RapidAPI host override |
| `SWISS_JOBS_BASE_URL` | `https://www.jobs.ch/en/vacancies/` | No | jobs.ch base URL |
| `JOBUP_BASE_URL` | `https://www.jobup.ch/en/jobs/` | No | jobup.ch base URL |
| `HTTP_TIMEOUT_SECONDS` | `15.0` | No | Per-source request timeout |
| `HTTP_MAX_RETRIES` | `3` | No | Tenacity retry attempts |
| `DEFAULT_RESULTS_PER_SOURCE` | `10` | No | Default limit per source fetch |
| `MAX_TOTAL_RESULTS` | `50` | No | Hard cap on merged results before ranking |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | No | OTLP gRPC endpoint for trace export |

The server crashes at startup if a `SecretStr`-typed field is required and missing. For optional sources, absence of the API key simply skips client registration — no crash.

---

## 11. Agent Integration

The agents layer connects via `HttpMCPClient` (defined in `agents/src/agents/market_intelligence/mcp_client.py`). Two agents use this server:

### Market Intelligence Agent

Calls `search_jobs` to retrieve live job postings for the target role and country, then feeds them into skill frequency analysis and market signal summarisation.

```python
raw = await mcp_client.call(
    "job_board",
    "search_jobs",
    {"role": "AI Systems Engineer", "country": "CH", "limit": 20},
    correlation_id=correlation_id,
)
# raw["postings"] → list of JobPosting dicts
```

Configured via `MCP_JOB_BOARD_URL` in the agents `.env`.

### Opportunity Matching Agent

Calls `search_jobs` filtered by the user's target role and location, then enriches each posting with LLM-scored fit against the user's `SkillGraph`. Also calls `get_job_detail` when full descriptions are needed for CV tailoring.

### Stub fallback

When `MCP_JOB_BOARD_URL` is not set, agents automatically use `StubMCPClient` which returns realistic mock postings without any network calls. This means agents can be developed and tested independently of the MCP server.

---

## 12. Path Resolution

The `job-board/` directory name contains a dash, making it non-importable as a Python package. Imports within the server use flat module names (e.g., `from models import JobPosting`, `from clients.base_client import ...`).

Shared modules are importable as `from shared.xxx import ...` because `server.py` inserts the parent `mcp-servers/` directory into `sys.path` at the top of the file before any other imports:

```python
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)
```

The pytest `conftest.py` does the same, adding both `mcp-servers/` and `mcp-servers/job-board/` to `sys.path` so tests resolve all imports without running the server.

---

## 13. Testing

Tests live in `mcp-servers/job-board/tests/test_server.py`. The test client drives the FastAPI app in-process using `fastapi.testclient.TestClient` — no network calls are made.

**Test doubles:**

- `_StubClient` — implements the same `search()`, `get_detail()`, `get_trending_roles()` interface as the real clients but returns controlled `JobPosting` and `TrendingRole` objects
- `stub_cache` — `AsyncMock` that returns `None` (cache miss) by default; individual tests override `stub_cache.get` to test cache-hit paths
- `stub_rate_limiter` — `AsyncMock` that allows all requests by default; set `return_value=False` to test rate-limit paths

**Test coverage by area:**

| Area | Tests |
|------|-------|
| Health endpoints (`/livez`, `/readyz`, `/metrics`) | 3 |
| JSON-RPC dispatch (parse error, method-not-found, invalid-request) | 3 |
| `search_jobs` (valid, invalid params, field shape, cache hit, rate limited) | 5 |
| `get_job_detail` (found, not found, invalid params) | 3 |
| `get_trending_roles` (valid, invalid country, multi-source merge) | 3 |
| Model unit tests (`JobPosting` dedup, `model_dump_api` shape) | 2 |
| **Total** | **20** |

**Running tests:**

```bash
cd mcp-servers/job-board
poetry install
poetry run pytest -v
```

---

## 14. Running Locally

```bash
# 1. Start Redis (needed for cache and rate limiter)
docker run -d -p 6379:6379 redis:7-alpine

# 2. Install dependencies
cd mcp-servers/job-board
poetry install

# 3. Configure environment
cat > .env << 'EOF'
ENVIRONMENT=development
LOG_LEVEL=DEBUG
REDIS_URL=redis://localhost:6379/1

# Optional — server works without these (Swiss Jobs always active)
LINKEDIN_API_KEY=your-rapidapi-key
INDEED_API_KEY=your-rapidapi-key
GLASSDOOR_API_KEY=your-rapidapi-key

# Optional — leave empty to disable auth in dev
MCP_API_KEY=
EOF

# 4. Run
uvicorn server:app --host 0.0.0.0 --port 3001 --reload
```

**Verify:**
```bash
curl http://localhost:3001/livez
# → {"status":"ok"}

curl -X POST http://localhost:3001/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"search_jobs","params":{"role":"Software Engineer","country":"CH","limit":5}}'
```

**Agents side:** add `MCP_JOB_BOARD_URL=http://localhost:3001` to `agents/.env`.

---

## 15. Docker

For production / Docker Compose:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY mcp-servers/shared /app/mcp-servers/shared
COPY mcp-servers/job-board /app/mcp-servers/job-board

WORKDIR /app/mcp-servers/job-board
RUN pip install poetry && poetry install --no-dev

ENV PYTHONPATH=/app/mcp-servers
EXPOSE 3001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3001"]
```

`PYTHONPATH=/app/mcp-servers` makes `from shared.xxx import ...` work without the in-process `sys.path` manipulation (which remains as a fallback for direct invocation).

Docker Compose service entry:
```yaml
mcp-job-board:
  build:
    context: .
    dockerfile: mcp-servers/job-board/Dockerfile
  ports: ["3001:3001"]
  environment:
    REDIS_URL: redis://redis:6379/1
    LINKEDIN_API_KEY: ${LINKEDIN_API_KEY}
    INDEED_API_KEY: ${INDEED_API_KEY}
    GLASSDOOR_API_KEY: ${GLASSDOOR_API_KEY}
    MCP_API_KEY: ${MCP_API_KEY}
  depends_on: [redis]
```

---

## 16. Architecture Decisions

### Sources fail independently

Each client's `search()` catches all exceptions and returns `[]`. `asyncio.gather(*tasks, return_exceptions=True)` ensures that a timeout on LinkedIn does not cancel the Indeed or Swiss Jobs fetches. The merged result is always the best available subset — never an outage propagation.

### Cache before fetch, always

The cache lookup happens after rate limiting but before any upstream call. A cache hit short-circuits everything — no source is queried, no ranking happens. This is the primary cost-reduction mechanism for repeated agent calls on the same role/country pair.

### Swiss Jobs needs no key

`jobs.ch` and `jobup.ch` are always registered. This ensures the server is never completely dark even in a dev environment with no API keys configured. Swiss market data (the primary target market for this system) is always available.

### `model_dump_api()` over `model_dump()`

The canonical Pydantic `model_dump()` output uses Python-native field names and types. The agents layer was written before the MCP server and expects specific field names (e.g., `url` not `source_url`, `posted_date` as an ISO string not a `date` object). `model_dump_api()` produces exactly the shape `JobBoardFetcher._parse_postings()` expects, decoupling the internal model from the wire format without changing the agent code.

### Rate limiting fails open

When Redis is down, the rate limiter always returns `True` (allowed). The alternative — failing closed (reject all requests) — would cause total agent failure during a Redis outage. The cache also fails open, which means Redis downtime degrades performance (more upstream calls) but does not break functionality.

### Auth is optional in dev

Setting `MCP_API_KEY=""` (or not setting it at all) bypasses authentication entirely. This makes local development frictionless — you run the server and the agents without configuring shared secrets. In production, `MCP_API_KEY` is injected as an environment secret and the auth check is active.
