<div align="center">

# 🔌 Career Roadmap AI — MCP Tool Servers

**Model Context Protocol · FastAPI JSON-RPC 2.0 · Redis cache · Python 3.12**

[![MCP CI](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-mcp-servers.yml?branch=main&style=flat-square&label=CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![JSON-RPC](https://img.shields.io/badge/JSON--RPC-2.0-gray?style=flat-square)](https://www.jsonrpc.org/specification)

</div>

Seven standalone FastAPI microservices that wrap external APIs as **permission-scoped, rate-limited, cacheable tool servers** for the agent pipeline. Each server speaks [Model Context Protocol](https://modelcontextprotocol.io) (JSON-RPC 2.0) and runs on its own port.

> **System overview:** See the [root README](../README.md) for the full architecture picture.
> **Agent integration:** See the [agents README](../agents/README.md) for how agents call these servers.

---

## Table of Contents

- [What are MCP servers?](#what-are-mcp-servers)
- [Server directory](#server-directory)
- [Shared architecture](#shared-architecture)
- [Local setup](#local-setup)
- [Running MCP servers](#running-mcp-servers)
- [JSON-RPC protocol](#json-rpc-protocol)
- [Observability](#observability)
- [Adding a new server](#adding-a-new-server)

---

## What are MCP servers?

MCP servers are the **data integration layer** between the agents and the outside world. Instead of each agent knowing how to call LinkedIn's API, handle rate limits, and cache responses, they delegate to purpose-built tool servers.

Each server:
- **Wraps one external domain** (jobs, courses, salaries, etc.)
- **Caches responses in Redis** — identical queries share a cached result for 10–60 minutes
- **Rate-limits callers** — token bucket per user per tool, respects provider limits
- **Degrades gracefully** — if an external API is down, returns a structured error so agents can fall back
- **Emits observability signals** — Prometheus metrics, OTel spans, and structured audit logs for every call

The agents call MCP servers over HTTP JSON-RPC 2.0. Kong routes `/mcp/<name>/**` to the right server. In dev, each server runs as a local process (outside Docker) for hot-reload.

---

## Server directory

| Port | Name | External APIs | Key tools |
|---|---|---|---|
| **3001** | [job-board](#job-board-3001) | LinkedIn (RapidAPI), Indeed, Glassdoor, jobs.ch | `search_jobs`, `get_job_details` |
| **3002** | [course-catalogue](#course-catalogue-3002) | Coursera, Udemy, edX, YouTube, O'Reilly | `search_courses`, `get_course_details` |
| **3003** | [github-trends](#github-trends-3003) | GitHub REST API (public), npm registry | `get_trending_repos`, `get_language_stats` |
| **3004** | [salary-benchmark](#salary-benchmark-3004) | Glassdoor, Levels.fyi, PayScale | `get_salary`, `get_salary_distribution` |
| **3005** | [social-signals](#social-signals-3005) | HackerNews (Algolia), Reddit, Twitter/X | `search_social`, `get_trending_topics` |
| **3006** | [calendar](#calendar-3006) | Google Calendar, Microsoft Outlook (Graph) | `create_event`, `search_events` |
| **3007** | [industry-news](#industry-news-3007) | NewsAPI, RSS feeds | `search_news`, `get_trending_articles` |

---

## Server details

### Job Board (3001)

Aggregates live job postings from multiple providers into a unified schema.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `search_jobs` | `role: str`, `location: str`, `skills: list[str]`, `limit: int` | Up to 50 job postings with title, company, salary range, required skills, posting date |
| `get_job_details` | `job_id: str`, `source: str` | Full job description, requirements, benefits, company info |

**External APIs:** LinkedIn Jobs (via RapidAPI), Indeed Job Search (via RapidAPI), Glassdoor, jobs.ch

**Cache TTL:** 30 minutes (job listings change frequently but not per-minute)

---

### Course Catalogue (3002)

Discovers and ranks learning resources across major platforms.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `search_courses` | `skill: str`, `level: str`, `format: str`, `limit: int` | Courses with title, provider, rating, price, duration, URL |
| `get_course_details` | `course_id: str`, `provider: str` | Full syllabus, prerequisites, student reviews, certification details |

**External APIs:** Coursera API, Udemy Affiliate API, edX Partner API, YouTube Data API v3, O'Reilly Learning

**Cache TTL:** 60 minutes (course catalogues are relatively stable)

---

### GitHub Trends (3003)

Surfaces trending technologies from GitHub without requiring authentication.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `get_trending_repos` | `language: str`, `timeframe: str` | Top repos by stars, forks, and growth rate |
| `get_language_stats` | `language: str` | GitHub usage stats, contributor count, fork trends |

**External APIs:** GitHub REST API (public endpoints, no auth required), npm download stats

**Cache TTL:** 60 minutes

---

### Salary Benchmark (3004)

Provides compensation data by role, location, experience level, and company size.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `get_salary` | `role: str`, `location: str`, `experience_years: int` | Median, p25, p75, p90 salary; equity ranges; bonus data |
| `get_salary_distribution` | `role: str`, `location: str` | Full distribution by company size, industry, and remote vs on-site |

**External APIs:** Glassdoor Salary (RapidAPI), Levels.fyi (scraper), PayScale API

**Cache TTL:** 24 hours (salary data changes slowly)

---

### Social Signals (3005)

Aggregates community sentiment and trending topics from developer communities.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `search_social` | `topic: str`, `platforms: list[str]` | Posts, comments, engagement metrics, sentiment score |
| `get_trending_topics` | `community: str`, `timeframe: str` | Trending topics with velocity and reach metrics |

**External APIs:** HackerNews (Algolia Search API), Reddit API, Twitter/X API v2

**Cache TTL:** 10 minutes (social signals move fast)

---

### Calendar (3006)

Integrates with calendar providers for scheduling and event discovery.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `create_event` | `title: str`, `start: datetime`, `end: datetime`, `description: str` | Created event ID and calendar URL |
| `search_events` | `topic: str`, `location: str`, `start_date: date`, `end_date: date` | Relevant conferences, meetups, and workshops |

**External APIs:** Google Calendar API, Microsoft Graph API (Outlook)

**Cache TTL:** 5 minutes for event search; no cache for write operations

---

### Industry News (3007)

Aggregates technology and industry news from multiple sources.

**Tools:**

| Tool | Parameters | Returns |
|---|---|---|
| `search_news` | `query: str`, `sector: str`, `days_back: int` | Articles with title, source, summary, sentiment, relevance score |
| `get_trending_articles` | `sector: str`, `timeframe: str` | Top articles by engagement in the past N days |

**External APIs:** NewsAPI, curated RSS feeds (TechCrunch, Wired, Hacker News Frontpage)

**Cache TTL:** 15 minutes

---

## Shared architecture

Every MCP server follows the same structure:

```
mcp-servers/<name>/
├── server.py            ← FastAPI app, JSON-RPC dispatcher, lifespan
├── tools/
│   ├── <tool_name>.py   ← One file per tool (provider calls, response normalisation)
│   └── cache.py         ← Redis cache wrapper (key generation, TTL management)
├── rate_limiter.py      ← Token bucket per user per tool
├── schemas.py           ← Tool request/response Pydantic models
├── config.py            ← Server settings (API keys, cache TTL, rate limits)
├── observability.py     ← Prometheus metrics + OTel tracer
├── tests/
│   └── test_<name>.py
├── Dockerfile
└── requirements.txt
```

### Required endpoints

Every server must expose:

| Endpoint | Method | Description |
|---|---|---|
| `/` | `POST` | JSON-RPC 2.0 dispatcher (tool router) |
| `/livez` | `GET` | Liveness probe → `{ "status": "ok" }` |
| `/readyz` | `GET` | Readiness probe (checks external API connectivity) |
| `/metrics` | `GET` | Prometheus scrape endpoint |

### Observability per call

Every tool call must emit:

```python
# Audit log (required for compliance)
logger.info(
    "mcp.tool.called",
    server="job-board",
    tool="search_jobs",
    user_id=user_id,
    cache_hit=cache_hit,
    duration_ms=duration,
    outcome="success" | "error",
)

# Prometheus metric
tool_calls_total.labels(
    server="job-board",
    tool="search_jobs",
    outcome="success",
).inc()
```

---

## Local setup

MCP servers run as local processes in development (outside Docker, for hot-reload).

```bash
# Install all MCP server dependencies (from monorepo root)
make install      # includes MCP server pip installs

# Or install individually (from mcp-servers/<name>/)
pip install -r requirements.txt
```

Each server reads its config from the shared `apps/api/.env` file.

---

## Running MCP servers

### Start all servers (recommended)

```bash
# From monorepo root
make mcp-up       # starts all 7 MCP servers as background processes

# Or with the full dev stack
make dev-full     # starts everything including MCP servers
```

### Start individually

```bash
# From mcp-servers/<name>/
uvicorn server:app --reload --port 3001   # adjust port per server

# Or via Makefile targets
make mcp-job-board        # :3001
make mcp-course-catalogue # :3002
make mcp-github-trends    # :3003
make mcp-salary-benchmark # :3004
make mcp-social-signals   # :3005
make mcp-calendar         # :3006
make mcp-industry-news    # :3007
```

### Kong routing

In dev, Kong routes `/mcp/<name>/**` to `http://host.docker.internal:<port>`. The Kong config is in `apps/api/kong/kong.dev.yml`.

In production, each server runs as a separate Azure Container App behind Kong.

---

## JSON-RPC protocol

All tools are called via `POST /` with a JSON-RPC 2.0 body:

```json
POST http://localhost:8080/mcp/job-board
Content-Type: application/json
Authorization: Bearer <firebase-id-token>

{
  "jsonrpc": "2.0",
  "method": "search_jobs",
  "params": {
    "role": "Senior Machine Learning Engineer",
    "location": "Zurich, Switzerland",
    "skills": ["Python", "PyTorch", "MLflow"],
    "limit": 20
  },
  "id": "req-abc-123"
}
```

Successful response:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "jobs": [...],
    "total": 47,
    "cache_hit": false,
    "fetched_at": "2025-05-23T10:00:00Z"
  },
  "id": "req-abc-123"
}
```

Error response (JSON-RPC 2.0 standard errors):

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "External API rate limit exceeded",
    "data": { "retry_after": 30 }
  },
  "id": "req-abc-123"
}
```

---

## Observability

Each server emits three types of signals:

```
Prometheus (GET /metrics on each server port)
    career_mcp_tool_calls_total{server, tool, outcome}
    career_mcp_tool_duration_seconds{server, tool}
    career_mcp_cache_hits_total{server, tool}
    career_mcp_external_api_errors_total{server, provider}

OTel spans
    mcp.<server>.<tool>
        → attributes: user_id, cache_hit, provider, result_count

Structlog audit events
    mcp.tool.called  →  server, tool, user_id, cache_hit, duration_ms, outcome
```

Prometheus scrapes all MCP servers via the `prometheus.yml` config in `apps/api/observability/prometheus/`.

---

## Testing

```bash
# From monorepo root
make test-mcp               # all MCP server tests

# From mcp-servers/<name>/
pytest tests/ -v
pytest tests/ -k "test_search" --no-header -q
```

Unit tests mock external API calls. Integration tests (tagged `@pytest.mark.integration`) hit real APIs and require valid keys in `.env`.

---

## Adding a new server

1. **Scaffold the directory** under `mcp-servers/<new-name>/` following an existing server (e.g. `calendar/` is a clean reference)
2. **Choose the next port** (current highest: `:3007` → use `:3008`)
3. **Implement `server.py`** with `/livez`, `/readyz`, `/metrics`, and `POST /` JSON-RPC dispatcher
4. **Add to Kong config** — both files must be updated:
   - `apps/api/kong/kong.dev.yml` (dev)
   - `infrastructure/kong/kong.yml` (production)
5. **Run `make gateway-reload`** to apply without restarting Docker
6. **Add to Prometheus scrape config** in `apps/api/observability/prometheus/prometheus.yml`
7. **Add the MCP URL env var** to `apps/api/.env.example` and `agents/src/agents/config.py`
8. **Write tests** in `mcp-servers/<name>/tests/`
9. **Write a Dockerfile** so it can deploy as an Azure Container App

> **Reference implementation:** The [Course Catalogue server](course-catalogue/) has the cleanest architecture and is the recommended starting point for new servers.
