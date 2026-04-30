# Career Roadmap AI — API

The FastAPI backend for Career Roadmap AI. Handles authentication, user
profiles, roadmaps, sessions, and serves as the primary interface between
the frontend, the agent runtime, and the MCP tool servers.

> **Status:** Early scaffolding — the application boots, exposes health
> and metrics endpoints, and is wired for observability. Domain endpoints
> (auth, roadmap, schedule, etc.) are not yet implemented.

---

## Quick start

```bash
# 1. Start Postgres + Redis
docker compose -f docker-compose.dev.yml up -d

# 2. Install dependencies (one-time)
poetry install

# 3. Configure environment
cp .env.example .env
# then edit .env and fill in JWT_SECRET_KEY and ANTHROPIC_API_KEY

# 4. Run the dev server
poetry run fastapi dev src/main.py
```

The API will be at <http://localhost:8000>. Interactive docs at
<http://localhost:8000/docs>.

---

## Stack

| Concern               | Choice                                    |
|-----------------------|-------------------------------------------|
| Language              | Python 3.12                               |
| Package management    | Poetry 2.x                                |
| Web framework         | FastAPI 0.119+ (async, ASGI)              |
| Validation            | Pydantic v2                               |
| ORM                   | SQLAlchemy 2.x async                      |
| Migrations            | Alembic (async-aware)                     |
| Database driver       | asyncpg                                   |
| Database              | PostgreSQL 16                             |
| Cache / queue / pubsub | Redis 7                                  |
| Background tasks      | Celery 5.x (Redis broker)                 |
| Auth                  | PyJWT, passlib (bcrypt)                   |
| LLM clients           | anthropic, openai, langchain, langgraph   |
| Error tracking        | Sentry SDK (with Anthropic + LangChain integrations) |
| Logging               | structlog (JSON in prod, pretty in dev)   |
| Metrics               | prometheus-client + prometheus-fastapi-instrumentator |
| Tracing               | OpenTelemetry (OTLP exporter)             |
| Linting / formatting  | Ruff                                      |
| Type checking         | mypy (strict mode)                        |
| Testing               | pytest + pytest-asyncio + factory-boy     |

---

## Prerequisites

- **Python** 3.12 (3.13 also works; **not 3.14**, some deps lack wheels)
- **Poetry** 2.0+ — [install instructions](https://python-poetry.org/docs/#installation)
- **Docker** 24+ with Docker Compose v2
- An **Anthropic API key** (only needed once you start exercising LLM-backed
  endpoints; a placeholder string is fine for the smoke test)

Recommended Poetry config (one-time, per machine):

```bash
poetry config virtualenvs.in-project true
```

This puts the venv at `.venv/` inside the project, which is easier to inspect
and matches the dev experience of `node_modules/`.

---

## Project layout

```
apps/api/
├── alembic/                     # Async-aware Alembic setup
│   ├── env.py                   # Wired to src.config.Settings + src.db.base.Base
│   └── versions/                # Migration files (one per change)
├── alembic.ini                  # Alembic config — sqlalchemy.url comes from env.py
├── docker-compose.dev.yml       # Postgres 16 + Redis 7 for local dev
├── pyproject.toml               # Poetry 2 / PEP 621 — deps + ruff/mypy/pytest config
├── .env.example                 # Template for environment variables (committed)
├── .env                         # Real env — gitignored
├── scripts/                     # One-off scripts (seeders, superuser, etc.)
├── tests/                       # Test suite
│   ├── conftest.py
│   ├── factories/               # factory-boy model factories
│   └── integration/             # End-to-end integration tests
└── src/
    ├── __init__.py
    ├── main.py                  # FastAPI entrypoint, lifespan, exception handlers
    ├── config.py                # Pydantic Settings (env-validated)
    ├── core/
    │   ├── exceptions.py        # AppException + subclasses
    │   ├── healthcheck.py       # /livez, /readyz
    │   └── logging.py           # structlog configuration
    ├── db/
    │   ├── base.py              # DeclarativeBase with id, created_at, updated_at
    │   └── session.py           # Async engine + get_db dependency
    ├── observability/
    │   ├── sentry.py            # Sentry init with AI integrations
    │   ├── metrics.py           # Prometheus + custom AI counters
    │   └── tracing.py           # OpenTelemetry setup
    ├── domains/                 # Domain-driven layout — one folder per bounded context
    │   ├── user/
    │   ├── roadmap/
    │   ├── schedule/
    │   ├── monthly_plan/
    │   ├── progress/
    │   ├── cv/
    │   ├── market/
    │   ├── networking/
    │   ├── books/
    │   ├── notifications/
    │   └── opportunities/
    ├── streaming/               # WebSocket + SSE handlers (planned)
    └── session/                 # Redis-backed session manager (planned)
```

### Domain structure

Each domain follows the same pattern:

```
domains/<name>/
├── model.py        # SQLAlchemy ORM models
├── schema.py       # Pydantic request/response schemas
├── repository.py   # Data access — no business logic
├── service.py      # Business logic — no HTTP, no SQL specifics
├── router.py       # FastAPI APIRouter — thin layer over service
└── tests/
    ├── test_service.py
    └── test_router.py
```

Routers depend on services. Services depend on repositories. Repositories
depend on the SQLAlchemy session. This keeps business logic testable
without HTTP or a real database.

---

## Configuration

All configuration is loaded from environment variables via
`pydantic-settings`. The single source of truth is `src/config.py`.

The full template is in `.env.example`. Six values are required for the
app to start:

| Variable                | Notes                                                  |
|-------------------------|--------------------------------------------------------|
| `DATABASE_URL`          | Async DSN: `postgresql+asyncpg://user:pass@host/db`    |
| `REDIS_URL`             | `redis://localhost:6379/0`                             |
| `CELERY_BROKER_URL`     | `redis://localhost:6379/1`                             |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2`                             |
| `JWT_SECRET_KEY`        | Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ANTHROPIC_API_KEY`     | From <https://console.anthropic.com/>                  |

### Generating a JWT secret

```bash
poetry run python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Sensitive values

`.env` is **gitignored**. Never commit it. Production secrets live in
Azure Key Vault (or equivalent); see `infrastructure/terraform/modules/key-vault/`.

---

## Running locally

### Start the dependencies

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps  # both should be "healthy"
```

This brings up:

- **Postgres 16** on `localhost:5432` (user `crai`, db `career_roadmap`)
- **Redis 7** on `localhost:6379`

Data persists across restarts in named Docker volumes (`api_postgres_data`,
`api_redis_data`).

### Start the API

```bash
poetry run fastapi dev src/main.py
```

The dev command auto-reloads on file changes. For a closer-to-production
run (no reload, multiple workers), use:

```bash
poetry run fastapi run src/main.py --workers 4
```

### Stop everything

```bash
# In the API terminal: Ctrl+C
docker compose -f docker-compose.dev.yml down       # stop containers
docker compose -f docker-compose.dev.yml down -v    # also delete data volumes
```

---

## Endpoints (current)

| Method | Path       | Purpose                                            |
|--------|------------|----------------------------------------------------|
| GET    | `/`        | App metadata (name, version, docs URL)             |
| GET    | `/livez`   | Liveness probe — process is up. No deps checked.   |
| GET    | `/readyz`  | Readiness probe — opens a DB connection            |
| GET    | `/metrics` | Prometheus-format metrics for scraping             |
| GET    | `/docs`    | Swagger UI (only in `development` / `debug=true`)  |
| GET    | `/redoc`   | ReDoc alternative docs                             |

Domain endpoints (`/api/v1/auth`, `/api/v1/roadmap`, etc.) will be added
incrementally as each domain is built.

---

## Database & migrations

### First-time setup

After your Postgres container is running and `.env` is configured:

```bash
# Confirm Alembic can connect — should show no errors, no revision yet
poetry run alembic current
```

### Creating a migration

After adding or changing a SQLAlchemy model, generate a migration:

```bash
poetry run alembic revision --autogenerate -m "add user table"
```

> **Important:** for autogenerate to detect a new model, you must import
> it inside `alembic/env.py`. The file has commented-out import lines —
> uncomment the relevant one when you add a domain.

### Applying migrations

```bash
poetry run alembic upgrade head     # apply all pending
poetry run alembic upgrade +1       # apply one
poetry run alembic downgrade -1     # roll back one
poetry run alembic history          # see all migrations
```

### Resetting the database (dev only)

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
poetry run alembic upgrade head
```

---

## Observability

The API is instrumented from day one — every request, query, and (later)
agent invocation is observable.

### Logging — structlog → stdout → Loki

- **Development:** human-readable console output with colours
- **Production:** structured JSON, one event per line
- Promtail (in the observability stack) tails container stdout and ships
  to Loki

To log from your code:

```python
from src.core.logging import get_logger

logger = get_logger(__name__)
logger.info("user.created", user_id=user.id, email=user.email)
```

Always log structured key-value pairs, not interpolated strings.

### Metrics — Prometheus

The `/metrics` endpoint exposes:

- **Default RED metrics** (rate, errors, duration) per HTTP handler, via
  `prometheus-fastapi-instrumentator`
- **Python runtime** metrics (GC, memory, etc.)
- **Custom AI counters** registered in `src/observability/metrics.py`:
  - `agent_invocations_total{agent_name,outcome}`
  - `llm_tokens_total{model,direction}`
  - `mcp_tool_calls_total{server,tool,outcome}`
  - `agent_duration_seconds{agent_name}` (histogram)

To increment these from agent code:

```python
from src.observability.metrics import agent_invocations_total

agent_invocations_total.labels(
    agent_name="cv_analysis", outcome="success"
).inc()
```

### Error tracking — Sentry (AI-aware)

Sentry catches unhandled exceptions and auto-instruments:

- FastAPI requests
- SQLAlchemy queries
- Redis calls
- **Anthropic Claude calls** — token counts, latency, cost per call
- **LangChain / LangGraph orchestration** — full agent traces with
  `gen_ai.*` semantic conventions

To enable, set `SENTRY_DSN` in `.env`. To capture prompts and responses
(useful for debugging but contains PII), also set
`SENTRY_SEND_DEFAULT_PII=true` — only after a privacy review.

### Tracing — OpenTelemetry

Distributed traces are exported via OTLP to Grafana Tempo (configured in
the observability stack — coming next). Traces complement Sentry: Sentry
focuses on errors and AI calls, OpenTelemetry covers the whole request
journey.

---

## Development workflow

### Linting and formatting

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and
formatting (replaces black, isort, flake8, pyupgrade in one tool):

```bash
poetry run ruff check src tests           # lint
poetry run ruff check --fix src tests     # lint + autofix
poetry run ruff format src tests          # format
```

### Type checking

```bash
poetry run mypy src
```

mypy is configured in **strict mode** in `pyproject.toml`. Don't suppress
errors with `# type: ignore` unless absolutely necessary; if you must,
include the specific error code: `# type: ignore[arg-type]`.

### Tests

```bash
poetry run pytest                            # run everything
poetry run pytest tests/integration          # one folder
poetry run pytest -k "test_user"             # match by name
poetry run pytest --cov=src --cov-report=html # coverage HTML report
```

### Pre-commit checklist

Before opening a PR:

```bash
poetry run ruff check src tests
poetry run ruff format src tests
poetry run mypy src
poetry run pytest
```

Or in one line:

```bash
poetry run ruff check src tests && poetry run ruff format src tests && poetry run mypy src && poetry run pytest
```

---

## Architecture notes

### Why FastAPI over Django REST Framework

- Native async + WebSocket support (we stream agent responses)
- Pydantic-first validation (same models for HTTP, DB, agents)
- OpenAPI generation is automatic and accurate
- Lower memory footprint, suited for many small concurrent agent calls

### Why async + asyncpg

The orchestrator dispatches multiple agents in parallel; many agents fan
out to multiple MCP servers; many MCP servers do live HTTP polling. Sync
I/O would force one-thread-per-request, which doesn't scale for this
workload pattern.

### Why structlog over standard logging

Agents produce highly structured events (which agent, which tool, which
user, which session, which model, how many tokens). Structured logs make
these queryable in Loki without regex parsing.

### Domain-driven layout

The `domains/` structure mirrors the architecture document's bounded
contexts (User, Roadmap, Schedule, CV, Market, Networking, etc.). Each
domain owns its model, schema, repository, service, router, and tests.
Cross-domain dependencies go through services, never models or
repositories — this keeps each domain independently testable and
refactorable.

---

## Related services

This API is one of three Python services in the backend:

- **`apps/api`** — this repo: HTTP/WS gateway, persistence, auth (you are here)
- **`agents/`** — Master Orchestrator + 10 specialist agents + Celery workers
- **`mcp-servers/`** — 8 MCP tool servers (job board, course catalogue, etc.)

In production, **Kong Gateway** sits in front of the API for routing,
auth, rate limiting, and CORS.

See [`docs/architecture/overview.md`](../../docs/architecture/overview.md)
for the full system diagram.

---

## Troubleshooting

### `ValidationError: 6 validation errors for Settings`

`.env` is missing or doesn't contain the required keys. Copy
`.env.example` to `.env` and fill in `JWT_SECRET_KEY` and
`ANTHROPIC_API_KEY` at minimum.

### `connection refused` on `/readyz`

Postgres isn't running. Start it:

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps  # confirm "healthy"
```

### `alembic init` fails with "Directory alembic already exists"

You created the empty `alembic/` folder before running init. Fix:

```bash
Remove-Item -Recurse -Force alembic   # PowerShell
# or: rm -rf alembic                  # bash
poetry run alembic init -t async alembic
```

Then re-apply our custom `env.py` (see "Database & migrations" above).

### Poetry can't find Python 3.12

```bash
poetry env use 3.12
poetry env info  # verify
```

If 3.12 isn't installed, get it from <https://www.python.org/downloads/>.

### `psycopg2` build errors on Windows

You shouldn't see these — we removed `psycopg2-binary` in favor of
`asyncpg` for everything. If `pyproject.toml` still references it,
remove the line and run `poetry lock && poetry install`.

---

## Roadmap (this service)

Tracked in the architecture document; high-level milestones:

- [x] Project scaffolding and observability bootstrap
- [ ] Auth domain (register, login, JWT, password reset)
- [ ] User domain (profile, preferences)
- [ ] CV upload + parsing endpoint
- [ ] Roadmap CRUD endpoints
- [ ] Session manager (Redis) + clarification flow
- [ ] WebSocket / SSE streaming for agent responses
- [ ] Schedule, monthly plan, progress, networking, market domains
- [ ] Background tasks (Celery) for nightly market intel jobs
- [ ] Production Dockerfile + Kubernetes manifests

---

## License

Proprietary — Career Roadmap AI. © Roger Jeasy Bavibidila, 2026.