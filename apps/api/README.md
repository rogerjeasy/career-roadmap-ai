<div align="center">

# 🔧 Career Roadmap AI — Backend API

**FastAPI · Python 3.12 · PostgreSQL · Redis · Firebase · Celery**

[![API CI](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-api.yml?branch=main&style=flat-square&label=CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Poetry](https://img.shields.io/badge/Poetry-2.x-60A5FA?style=flat-square&logo=poetry&logoColor=white)](https://python-poetry.org)

</div>

The HTTP gateway layer of the Career Roadmap AI platform. It handles authentication, request validation, session management, domain business logic, and bridges the frontend to the LangGraph agent pipeline via Celery tasks and Server-Sent Events.

> **System overview:** See the [root README](../../README.md) for the full architecture picture.
> **Deep-dive patterns:** See [`.claude/backend-patterns.md`](../../.claude/backend-patterns.md) for repository design, agent pipeline internals, and domain conventions.

---

## Table of Contents

- [Architecture position](#architecture-position)
- [Directory structure](#directory-structure)
- [Prerequisites](#prerequisites)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Running the API](#running-the-api)
- [API endpoints](#api-endpoints)
- [Kong API Gateway](#kong-api-gateway)
- [Database](#database)
- [Observability](#observability)
- [Testing](#testing)
- [Code quality](#code-quality)
- [Adding a new domain](#adding-a-new-domain)

---

## Architecture position

```
Browser → Kong API Gateway (:8080) → FastAPI (:8000) → Celery workers → Agent pipeline
                                           │
                              ┌────────────┼──────────────┐
                              ▼            ▼               ▼
                         PostgreSQL      Redis         Firestore
                         (relational)   (sessions,    (user profiles,
                                         Celery)       roadmaps)
```

Kong sits in front of FastAPI and handles all cross-cutting infrastructure concerns (rate limiting, CORS, security headers, OTel root spans). FastAPI focuses purely on business logic.

---

## Directory structure

```
apps/api/
├── src/
│   ├── main.py                  ← FastAPI app, lifespan hooks, middleware stack
│   ├── config.py                ← pydantic-settings Settings (validated at startup)
│   ├── core/
│   │   ├── auth.py              ← get_current_user() FastAPI dependency (Firebase)
│   │   ├── exceptions.py        ← AppException hierarchy (NotFoundError, AuthError…)
│   │   ├── middleware.py        ← TraceContext, CaseConversion, CORS middleware
│   │   └── logging.py           ← configure_logging() + get_logger()
│   ├── db/
│   │   ├── session.py           ← Async SQLAlchemy engine + get_db() dependency
│   │   ├── firestore.py         ← get_firestore_client() dependency
│   │   ├── redis.py             ← get_redis() dependency
│   │   └── http.py              ← get_http_client() (shared httpx.AsyncClient)
│   ├── domains/                 ← One directory per business domain
│   │   ├── user/
│   │   ├── cv/
│   │   ├── roadmap/
│   │   ├── market/
│   │   ├── progress/
│   │   ├── networking/
│   │   ├── opportunities/
│   │   ├── monthly_plan/
│   │   ├── schedule/
│   │   ├── books/
│   │   └── notifications/
│   ├── session/                 ← Redis-backed session manager
│   ├── endpoints/
│   │   └── v1/                  ← HTTP controllers (one file per domain)
│   └── observability/
│       ├── metrics.py           ← Custom Prometheus counters + histograms
│       ├── tracing.py           ← OTel setup
│       └── sentry.py            ← Sentry initialisation
├── kong/
│   └── kong.dev.yml             ← Kong declarative config (dev, DB-less)
├── observability/
│   ├── grafana/                 ← Provisioning files + two pre-built dashboards
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── docker-compose.obs.yml
├── docker-compose.dev.yml       ← PostgreSQL + Redis + Kong + observability stack
├── pyproject.toml
└── .env.example                 ← Full list of environment variables with comments
```

### Domain directory convention

Every domain under `src/domains/<name>/` follows the same structure:

```
domains/<name>/
├── model.py                 ← SQLAlchemy ORM model (extends Base)
├── repository.py            ← SQLAlchemy repository (injected AsyncSession)
├── firestore_repository.py  ← Firestore repository (where applicable)
├── schemas.py               ← Pydantic v2 request/response models (no ORM coupling)
├── service.py               ← Business logic + async def get_<name>_service() dep
└── tests/
```

Controllers live in `src/endpoints/v1/<name>_controller.py` and are registered in `src/endpoints/v1/__init__.py`.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12+ |
| Poetry | 2.x |
| Docker Desktop | latest |
| `deck` CLI *(production Kong management)* | 2.x |

---

## Local setup

### 1. Install dependencies

```bash
cd apps/api
poetry install
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` — at minimum, set:

```env
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
FIREBASE_WEB_API_KEY=your-web-api-key
ANTHROPIC_API_KEY=sk-ant-...
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
DATABASE_URL=postgresql+asyncpg://crai:crai_dev_password@localhost:5432/career_roadmap
```

> See the [full environment variables reference](#environment-variables) below.

### 3. Place the Firebase service account

Download your service account JSON from the Firebase Console → Project Settings → Service accounts → Generate new private key.

Save it at `apps/api/firebase-service-account.json` (gitignored — never commit this file).

---

## Running the API

### Option A — Full stack with gateway and observability (recommended)

```bash
# From the monorepo root
make dev-full
# Starts: PostgreSQL · Redis · Kong (:8080) · Prometheus · Loki · Tempo · Grafana · FastAPI (:8000)
```

### Option B — Core infra + FastAPI only

```bash
make infra-up    # PostgreSQL + Redis
make dev         # FastAPI hot-reload on :8000
```

### Option C — FastAPI standalone (from apps/api/)

```bash
# Assumes PostgreSQL + Redis are already running
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload --port 8000
```

### Celery worker (separate terminal — required for roadmap generation)

```bash
# From monorepo root
make worker

# Or directly (from apps/api/)
poetry run celery -A agents.bus.celery_app worker --loglevel=info
# Windows: --pool=solo is added automatically by the Makefile
```

### Health checks

```
GET http://localhost:8000/livez   → { "status": "ok" }
GET http://localhost:8000/readyz  → { "status": "ok", "checks": { ... } }
```

### API docs (dev only, when DEBUG=true)

```
GET http://localhost:8000/docs    → Swagger UI
GET http://localhost:8000/redoc   → ReDoc
```

---

## Environment variables

Full reference — see `.env.example` for inline comments and all defaults.

### Required

| Variable | Description |
|---|---|
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | Path to service account JSON (dev) |
| `FIREBASE_CREDENTIALS_JSON` | Inline JSON string (CI / cloud deployments) |
| `FIREBASE_WEB_API_KEY` | Firebase Web API key (email/password auth) |
| `ANTHROPIC_API_KEY` | Anthropic API key — primary LLM provider |
| `REDIS_URL` | Redis DSN for app sessions and rate limiter |
| `CELERY_BROKER_URL` | Redis DSN for Celery task broker |
| `CELERY_RESULT_BACKEND` | Redis DSN for Celery task results |

> One of `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` is required.

### Optional — with defaults

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `false` | Enables `/docs`, `/redoc`, verbose logging |
| `DATABASE_URL` | — | PostgreSQL async DSN |
| `OPENAI_API_KEY` | — | OpenAI fallback LLM |
| `DEEPSEEK_API_KEY` | — | DeepSeek fallback LLM |
| `PINECONE_API_KEY` | — | Pinecone vector database (RAG) |
| `COHERE_API_KEY` | — | Cohere reranker (optional, improves RAG quality) |
| `CLOUDINARY_URL` | — | Cloudinary DSN (CV document storage) |
| `SENTRY_DSN` | — | Sentry error tracking DSN |
| `OTEL_TRACING_ENABLED` | `false` | Enable OpenTelemetry trace export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP gRPC endpoint (`http://localhost:4317`) |
| `RATE_LIMIT_PER_MINUTE` | `60` | App-level per-IP rate limit |
| `COMPLETENESS_THRESHOLD` | `0.75` | Min score to proceed without clarification |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Max clarification rounds before proceeding |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array (must be JSON-parseable) |

> **Windows:** `CORS_ORIGINS` must be a JSON array string: `CORS_ORIGINS=["http://localhost:3000"]`. Plain comma-separated strings fail pydantic-settings v2 parsing.

---

## API endpoints

All endpoints are exposed through Kong at `http://localhost:8080` in dev. FastAPI is reachable directly at `:8000` for quick `curl` but CORS is only fully configured at the gateway.

### Authentication

| Method | Path | Auth required | Description |
|---|---|---|---|
| `POST` | `/auth/register` | No | Register with email/password |
| `POST` | `/auth/login` | No | Sign in with email/password |
| `POST` | `/auth/google` | No | Sign in with Google OAuth |
| `POST` | `/auth/refresh` | No | Refresh Firebase ID token |
| `POST` | `/auth/logout` | Yes | Invalidate session |

### User

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/users/me` | Get current user profile |
| `PATCH` | `/api/v1/users/me` | Update current user profile |

### Session & Conversation

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/session` | Load current session state |
| `POST` | `/api/v1/session/message` | Append a conversation turn |
| `GET` | `/api/v1/session/profile` | Get enriched user profile context |
| `PATCH` | `/api/v1/session/profile` | Update profile context |
| `POST` | `/api/v1/session/clarification/reply` | Submit clarification answers |
| `DELETE` | `/api/v1/session` | Reset session |

### Orchestration & Streaming

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/orchestrator/generate` | Trigger roadmap generation (async, returns `request_id`) |
| `GET` | `/api/v1/orchestrator/status/{request_id}` | Poll Celery task status |
| `GET` | `/stream/{session_id}` | SSE stream of live agent events |

#### Roadmap generation flow

```
1. POST /api/v1/orchestrator/generate
   Response: { request_id, stream_channel, status: "queued" }

2. Open EventSource → GET /stream/{session_id}
   Receive AgentEvents in real time as each agent completes

3. On CLARIFICATION_REQUIRED event:
   → Surface questions in UI
   → POST /api/v1/session/clarification/reply  { "answers": [...] }
   → POST /api/v1/orchestrator/generate again (enriched profile auto-loaded from session)

4. ORCHESTRATION_COMPLETED carries the full roadmap in its payload
```

### MCP Tools (JSON-RPC 2.0)

| Method | Path | Tools |
|---|---|---|
| `POST` | `/mcp/job-board` | `search_jobs`, `get_job_details` |
| `POST` | `/mcp/course-catalogue` | `search_courses`, `get_course_details` |
| `POST` | `/mcp/github-trends` | `get_trending_repos`, `get_language_stats` |
| `POST` | `/mcp/salary-benchmark` | `get_salary`, `get_salary_distribution` |
| `POST` | `/mcp/social-signals` | `search_social`, `get_trending_topics` |
| `POST` | `/mcp/calendar` | `create_event`, `search_events` |
| `POST` | `/mcp/industry-news` | `search_news`, `get_trending_articles` |

### Health & Observability

| Method | Path | Description |
|---|---|---|
| `GET` | `/livez` | Liveness probe |
| `GET` | `/readyz` | Readiness probe (checks DB, Redis, Firebase) |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

---

## Kong API Gateway

| Concern | Kong | FastAPI |
|---|---|---|
| TLS termination | Yes (Azure ingress in prod) | — |
| Rate limiting | Global per-IP + per-route overrides | Per-user domain limits (slowapi) |
| CORS | Primary handler | Defense-in-depth fallback |
| Routing | All 8 services unified | Single-app routing |
| OTel tracing | Root span at gateway entry | Child spans (business logic) |
| Authentication | Passthrough | Firebase Admin SDK (`get_current_user()`) |
| Security headers | HSTS, X-Frame-Options, CSP | — |

### Dev commands

```bash
make gateway-up       # Start Kong (DB-less, reads kong/kong.dev.yml)
make gateway-reload   # Reload config without restart (after editing kong.dev.yml)
make gateway-logs     # Tail Kong access + error logs
make gateway-admin    # Smoke test: curl localhost:8001/routes
```

### Production (deck)

```bash
cp infrastructure/kong/deck.env.example infrastructure/kong/.env.production
make deck-diff    # Dry run diff against live Kong cluster
make deck-sync    # Push infrastructure/kong/kong.yml to production
```

---

## Database

### Migrations (Alembic)

```bash
make db-migrate              # Upgrade to latest (alembic upgrade head)
make db-rollback             # Roll back one revision

# Create a new migration:
poetry run alembic revision --autogenerate -m "add_user_preferences"
poetry run alembic upgrade head
```

### Redis key layout

| DB | Key pattern | Purpose | TTL |
|---|---|---|---|
| 0 | `session:{uid}` | User session (conversation history, clarification state, profile context) | 24h sliding |
| 1 | Celery keys | Task broker | N/A |
| 2 | Celery keys | Task results | 1h |
| 9 | Kong keys | Rate-limiting counters | Per window |

Session state is accessed exclusively through `src/session/manager.py`. Controllers never touch Redis directly.

---

## Observability

Every new endpoint must include all three observability signals:

### Metrics

```python
from src.observability.metrics import my_counter, my_histogram

my_counter.labels(status="success").inc()
with my_histogram.labels(operation="generate").time():
    result = await service.generate(...)
```

### Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("service.generate_roadmap") as span:
    span.set_attribute("user.id", uid)
```

### Structured logging

```python
from src.core.logging import get_logger

logger = get_logger(__name__)
logger.info("roadmap.generation.started", user_id=uid, session_id=sid)
logger.error("roadmap.generation.failed", error=str(exc), user_id=uid)
```

OTel `trace_id` and `span_id` are automatically bound by `TraceContextMiddleware`.

### Full stack

```bash
make gateway-obs-up   # Kong + Prometheus + Loki + Tempo + Grafana
```

| Service | URL |
|---|---|
| Grafana | http://localhost:3300 |
| Prometheus | http://localhost:9090 |
| Tempo | http://localhost:3200 |
| Loki | http://localhost:3100 |

---

## Testing

```bash
# From monorepo root
make test-api                   # All API tests

# From apps/api/ (selective)
poetry run pytest                                # All tests
poetry run pytest src/domains/roadmap/tests/     # One domain
poetry run pytest -k "test_generate" -v          # Filter by name

# With real services (integration)
docker compose -f docker-compose.dev.yml up -d
poetry run pytest tests/integration/ -v
```

---

## Code quality

```bash
make lint        # ruff check + format check
make format      # ruff format (auto-fix)

poetry run ruff check src/
poetry run mypy src/
```

---

## Adding a new domain

1. `src/domains/<name>/model.py` — SQLAlchemy model extending `Base`
2. `src/domains/<name>/repository.py` — `class <Name>Repository(AsyncSession)`
3. `src/domains/<name>/schemas.py` — Pydantic v2 models (no ORM coupling)
4. `src/domains/<name>/service.py` — `class <Name>Service` + FastAPI dependency
5. `src/endpoints/v1/<name>_controller.py` — `APIRouter`; register in `__init__.py`
6. `src/domains/<name>/tests/` — unit tests for service + repository

Every new endpoint must add Prometheus metrics, OTel spans, and structlog events. See [CLAUDE.md §8](../../CLAUDE.md#8-observability-stack-always-include-when-building-features) for the required pattern.
