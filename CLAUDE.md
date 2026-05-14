# Career Roadmap AI — Claude Code Session Guide

> **Auto-loaded each session.** Read this before touching any file so you never need to scan the full codebase cold.
> Extended backend patterns, domain deep-dives, and agent internals live in `.claude/backend-patterns.md`.
> Extended frontend patterns, component conventions, and real-time data flows live in `.claude/frontend-patterns.md`.

---

## 1. What This System Does

An **agentic career coaching platform**. A user describes their career goal; the system runs a multi-agent LangGraph pipeline (on Celery workers) that builds a personalised, week-by-week career roadmap. Results stream back to the browser via Server-Sent Events.

Architecture reference documents (HTML, read with a browser or VS Code Live Preview):
- Full agentic architecture: `documentation/architecture-design/career-roadmap-agentic-backend-architecture.html`
- System architecture overview: `documentation/architecture-design/career-roadmap-architecture(1).html`
- Project description (DOCX): `documentation/documents/career-roadmap-ai-merged.docx`

Implementation summaries per agent: `documentation/implementation_summaries/`

---

## 2. Monorepo Layout

```
career-roadmap-ai/
├── apps/
│   ├── api/          ← FastAPI backend (Python 3.12+, Poetry)
│   └── web/          ← Next.js 16 frontend (see apps/web/CLAUDE.md)
├── agents/           ← LangGraph multi-agent pipeline (Python, shared Poetry ws)
├── mcp-servers/      ← 7 MCP tool servers (Python)
├── packages/
│   ├── shared-types/ ← TypeScript types shared by web + API contracts
│   └── ui/           ← shadcn component library
├── infrastructure/   ← Docker, Terraform, deployment scripts
├── docs/             ← Architecture ADRs and developer guides
└── documentation/    ← HTML architecture diagrams and DOCX project description
```

---

## 3. Frontend Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 — App Router, React 19 |
| Language | TypeScript (strict mode) |
| Styling | Tailwind CSS v4 |
| Component library | shadcn/ui (Radix primitives) |
| Client state | Zustand (`zustand/middleware` — `persist`, `immer`) |
| Server state / cache | TanStack Query v5 |
| Schema validation | Zod v3 |
| Forms | React Hook Form v7 + `@hookform/resolvers/zod` |
| HTTP client | Axios (with Firebase token interceptor) |
| Real-time (SSE) | `EventSource` wrapper in `src/lib/sse.ts` |
| Real-time (WS) | Native WebSocket wrapper in `src/lib/websocket.ts` |
| Auth | Firebase JS SDK v10 (`firebase/auth`) |
| Fonts | Geist + Geist Mono (`next/font/google`) |
| Notifications | Sonner |

Node version: `>=20`. Package manager: `npm` (workspace root) or `pnpm`.

Frontend patterns deep-dive: `.claude/frontend-patterns.md`.

---

## 3a. Frontend Directory Map (`apps/web/src/`)

```
app/
  (auth)/              ← public auth pages (login, register, forgot-password)
  (app)/               ← protected app shell — all pages behind auth guard
    layout.tsx         ← loads auth guard + app shell (sidebar, header)
    dashboard/
    roadmap/
    coach/
    cv-analysis/
    market/
    opportunities/
    networking/
    progress/
    schedule/
    monthly-plan/
    books/
    settings/
  api/                 ← Next.js Route Handlers (BFF layer where needed)
  layout.tsx           ← root layout: fonts, <Providers />, <ConditionalShell />
  globals.css

components/
  ui/                  ← shadcn/ui primitives (never edit directly)
  layout/              ← sidebar, header, breadcrumbs, mobile-nav, conditional-shell
  coach/               ← chat window, chat message, typing indicator
  cv-analysis/         ← upload dropzone, gap report, readiness meter
  dashboard/           ← stat card, phase summary, quick actions, events widget
  market/              ← signal card, salary card, trending skills chart
  networking/          ← contact card, contact form, event calendar
  opportunities/       ← job card, match score badge
  roadmap/             ← phase card, week timeline, milestone badge
  progress/            ← habit streak, weekly review form
  shared/              ← confirm-dialog, error-boundary, loading-spinner, empty-state

hooks/                 ← custom React hooks (one concern per file)
lib/
  api/                 ← one file per backend domain (client.ts = axios instance)
  firebase.ts          ← Firebase app + auth singleton
  auth.ts              ← client-side auth helpers
  sse.ts               ← SSE manager
  websocket.ts         ← WebSocket manager
  cn.ts                ← cn() utility (clsx + tailwind-merge)
  constants.ts         ← ROUTE_PATHS, QUERY_KEYS, EVENT_TYPES
  date.ts              ← date formatting helpers (wraps date-fns)
  utils.ts             ← misc pure utilities
  validations.ts       ← Zod schemas reused across features

providers/             ← React context providers (composed in providers/index.tsx)
store/                 ← Zustand stores (one file per slice)
styles/                ← global CSS overrides
types/                 ← TypeScript interfaces (no Zod schemas here)
```

---

## 4. Backend Tech Stack

| Layer | Technology |
|---|---|
| HTTP framework | FastAPI (ASGI, Starlette) |
| Auth | Firebase Admin SDK + Firebase REST API |
| Primary DB | Firestore (async) |
| Relational DB | PostgreSQL + SQLAlchemy 2 async + Alembic |
| Cache / Session | Redis (aioredis) |
| Task queue | Celery + Redis broker |
| Agent orchestration | LangGraph (StateGraph) |
| LLM | Anthropic Claude (primary), OpenAI (fallback) |
| External tools | MCP protocol servers |
| Metrics | Prometheus (`/metrics`) + `prometheus-fastapi-instrumentator` |
| Distributed tracing | OpenTelemetry → OTLP (Grafana Tempo / Jaeger) |
| Error tracking | Sentry (FastAPI + Celery integration) |
| Structured logging | structlog (JSON in prod, console in dev) |
| Rate limiting | slowapi (Redis-backed, per-IP) |

Python version: `>=3.12,<3.14`. Package manager: Poetry.

---

## 5. Three-Layer Architecture

### L1 — HTTP Gateway (`apps/api/src/`)

Entry: `src/main.py`. Middleware stack (outermost → innermost):
1. `TraceContextMiddleware` — binds OTel `trace_id`/`span_id` into structlog context vars
2. `CaseConversionMiddleware` — camelCase→snake_case on request bodies/query params, snake_case→camelCase on JSON responses
3. `CORSMiddleware` — configured from `CORS_ORIGINS` env var
4. SlowAPI rate limiter — Redis-backed, 429 on excess

Startup lifespan: creates Redis connection pool, shared `httpx.AsyncClient`, initialises Firebase Admin SDK.

Key modules:
```
src/config.py            — pydantic-settings Settings (validated at startup, lru_cache singleton)
src/core/auth.py         — get_current_user() FastAPI dep, AuthenticatedUser dataclass
src/core/exceptions.py   — AppException hierarchy (NotFoundError, AuthenticationError, etc.)
src/core/middleware.py   — all middleware classes
src/core/logging.py      — configure_logging() + get_logger()
src/observability/       — setup_prometheus(), setup_tracing(), setup_sentry()
src/db/
  session.py             — async SQLAlchemy engine + get_db() dependency
  firestore.py           — get_firestore_client() dependency
  redis.py               — get_redis() dependency
  http.py                — get_http_client() dependency
```

### L2 — Domain Services (`apps/api/src/domains/` + `src/session/` + `src/endpoints/`)

Organised by domain. Each domain follows this structure:
```
domains/<name>/
  model.py          ← SQLAlchemy ORM model (or Pydantic dataclass)
  repository.py     ← SQLAlchemy repository
  firestore_repository.py  ← Firestore repository (where applicable)
  schemas.py        ← Pydantic request/response schemas
  service.py        ← Business logic; injected via FastAPI Depends
  __init__.py
  tests/
```

Implemented domains: `user`, `cv`, `market`, `roadmap`, `progress`, `networking`, `opportunities`, `monthly_plan`, `schedule`, `books`, `notifications`.

Controllers live in `src/endpoints/v1/`:
```
auth_controller.py          — /auth/register, /login, /google, /refresh, /logout
user_controller.py          — /users/me, /users/me (PATCH)
session_controller.py       — /sessions (create, get, delete)
orchestrator_controller.py  — /orchestrator/generate (202), /orchestrator/status/{id}
stream_controller.py        — /stream/{session_id} (SSE)
```

Session state (`src/session/`): Redis-backed `SessionManager`. Key = `session:{user_id}`. Sliding 24h TTL. Stores conversation history, clarification queue, user profile context, and plan context. All operations are `async`.

### L3 — Agent Pipeline (`agents/src/agents/`)

Full deep-dive in `.claude/backend-patterns.md § Agent Pipeline`.

---

## 6. Domain File Convention

When adding a new domain in `apps/api/src/domains/<name>/`:
1. `model.py` — SQLAlchemy model extending `Base` (from `src/db/base.py`)
2. `repository.py` — `class <Name>Repository` with `__init__(self, session: AsyncSession)`
3. `firestore_repository.py` — if Firestore-backed; `class Firestore<Name>Repository`
4. `schemas.py` — Pydantic v2 models; no ORM coupling
5. `service.py` — `class <Name>Service`; expose `async def get_<name>_service(...) -> <Name>Service` FastAPI dep
6. Controller in `src/endpoints/v1/<name>_controller.py`; register in `src/endpoints/v1/__init__.py`
7. Tests in `domains/<name>/tests/`

---

## 7. Coding Standards

### Frontend non-negotiables (enforced on every component, every PR)

These three rules are co-enforced — a component is **not complete** until all three pass:

1. **Full responsiveness.** Every component renders without content overflow or element overlap at every screen size from 375 px to 1536 px+. Design mobile-first using Tailwind's `sm:` / `md:` / `lg:` breakpoint prefixes. Use `min-w-0` on flex/grid children, `truncate` / `break-words` on user-generated text, and `max-w-*` + `w-full` instead of fixed pixel widths.

2. **TypeScript strict mode.** Every prop, return type, hook input, and API boundary must be explicitly typed. Export a `<Name>Props` interface from every component file. Zero `tsc` errors permitted (`npm run typecheck` must pass).

3. **No inline CSS.** Never use `style={{}}` for layout, spacing, colour, or typography. All styling goes through Tailwind utility classes (and `cn()` for merging). The only permitted exception is dynamic CSS custom properties — and even those must be consumed by a Tailwind arbitrary value, not raw inline style logic.

Full patterns and examples: `.claude/frontend-patterns.md §§ 9–10`.

### Backend design principles
- **High cohesion, low coupling.** Each module has one clear responsibility. Controllers never touch the DB; services never import controllers; repositories never import services.
- **Dependency injection over globals.** All shared resources (Redis, Firestore, HTTP client, DB session) are injected via FastAPI `Depends`. Never import `app.state` directly.
- **Async by default.** All I/O paths are `async def`. No `time.sleep()`; use `asyncio.sleep()`.
- **Pydantic-first.** All data that crosses a service or API boundary uses Pydantic models. Never pass raw `dict` between layers.
- **Fail loud at startup.** Config validation happens in `Settings` (pydantic-settings). Missing env vars crash the process immediately, not at first use.

### Structured logging
Use `get_logger(__name__)` from `src/core/logging.py` (or `agents/src/agents/core/logging.py`).
Always log with keyword arguments (structlog style):
```python
logger.info("user.registered", uid=firebase_uid, email=email)
logger.error("orchestrator.dispatch_failed", error=str(exc), user_id=user.uid)
```
OTel `trace_id` and `span_id` are automatically bound by `TraceContextMiddleware`.

### Error handling
Raise domain exceptions from `src/core/exceptions.py`. The global handler in `main.py` translates them to JSON `{"error_code": "...", "detail": "..."}`. Never raise bare `Exception` in service or controller code.

### Secrets
All secrets come from environment variables validated by `Settings`. Never hardcode keys. For development, use `.env` file (git-ignored). For production, use environment injection or a secret manager.

---

## 8. Observability Stack (always include when building features)

Every new agent, service method, or controller endpoint must include:

### Metrics (Prometheus)
Custom counters and histograms live in `apps/api/src/observability/metrics.py` (API layer) and `agents/src/agents/core/observability.py` (agent layer). Pattern:
```python
from prometheus_client import Counter, Histogram

my_counter = Counter("career_agents_<name>_total", "...", ["label"])
my_histogram = Histogram("career_agents_<name>_duration_seconds", "...", ["label"])
```
Scrape endpoint: `GET /metrics` (excluded from auth middleware).

### Tracing (OpenTelemetry)
Use `tracer.start_as_current_span("span.name")` for significant operations. Record exceptions with `span.record_exception(exc)` and set `StatusCode.ERROR`. Spans auto-propagate via FastAPI + SQLAlchemy + Redis instrumentors.

### Sentry
Initialised before the app in `main.py`. Celery workers init Sentry in their worker startup. No manual calls needed for exceptions — the SDK captures them automatically.

### Structured logs
Every important state transition emits a structlog event with all relevant IDs (`user_id`, `session_id`, `task_id`, `correlation_id`).

---

## 9. Security, Privacy, and Responsible AI

### Authentication & authorisation
- Firebase ID tokens (short-lived, ~1h) in `Authorization: Bearer <token>` header.
- Token verification via `get_current_user()` FastAPI dependency (`src/core/auth.py`).
- Refresh tokens exchanged via `POST /auth/refresh`; never stored server-side.
- All protected endpoints depend on `get_current_user()`. Never bypass it.
- Per-user row-level isolation: repository queries always filter by the authenticated `uid`. Never query without a user scope in multi-tenant collections.

### Data security
- Encryption at rest for uploaded CV documents and sensitive profile fields.
- Secrets managed outside code via environment variables or a secret manager. Never commit `.env` with real values.
- Uploaded document storage: configurable provider (`local` | `azure` | `s3`) via `BLOB_STORAGE_PROVIDER` env var.

### Rate limiting
Applied in middleware before CORS. Default: 60 req/min per IP (configurable via `RATE_LIMIT_PER_MINUTE`). Auth, chat, generation, and MCP tool endpoints are all rate-limited.

### MCP tool-call audit logs
Every MCP server call must emit a structured log event with the tool name, server, user ID, and outcome. The audit trail must be queryable.

### Responsible AI controls
- **No protected attribute inference.** Do not infer or act on race, gender, age, nationality, disability, or any protected characteristic. Do not reduce ambition or opportunity recommendations based on them.
- **Expose uncertainty.** Agents must surface confidence levels and assumptions in their outputs rather than presenting uncertain recommendations as facts.
- **User data control.** Users can delete documents and derived analyses. Implement soft-delete for roadmaps and agent outputs; hard-delete for uploaded documents.
- **Consent-gated external connections.** Require explicit user consent before connecting external accounts (LinkedIn, GitHub, calendar).
- **Human approval gate.** Write actions (calendar events, outreach messages) and critical plan changes require a human confirmation step before execution.
- **Explanations for recommendations.** Every significant recommendation (skill to learn, job to apply for, person to reach out to) must include a human-readable explanation of why.

---

## 10. Running the Backend Locally

```bash
# From apps/api/
poetry install
cp .env.example .env   # fill in real values
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL + Redis + Firestore emulator
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload --port 8000

# Workers (separate terminal)
poetry run celery -A agents.bus.celery_app worker --loglevel=info
```

Health check: `GET /livez` and `GET /readyz`.
API docs (dev only): `GET /docs` (Swagger), `GET /redoc`.

---

## 10a. Running the Frontend Locally

```bash
# From apps/web/
npm install
cp .env.local.example .env.local   # fill in Firebase config + API URL
npm run dev                         # starts on http://localhost:3000
```

The dev proxy in `next.config.ts` forwards `/api/v1/**` to `http://localhost:8000` so you don't need CORS config locally.

---

## 11. Key Environment Variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL async DSN |
| `REDIS_URL` | Redis DSN (sessions, rate limiter, Celery broker) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery Redis URLs |
| `FIREBASE_PROJECT_ID` | Firebase project |
| `FIREBASE_CREDENTIALS_PATH` | Service account JSON path (dev) |
| `FIREBASE_CREDENTIALS_JSON` | Service account JSON string (CI/cloud) |
| `FIREBASE_WEB_API_KEY` | Firebase REST API key (email/password auth) |
| `ANTHROPIC_API_KEY` | Primary LLM provider |
| `SENTRY_DSN` | Error tracking |
| `OTEL_TRACING_ENABLED` | Enable OTel export (default: false in dev) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC endpoint |
| `PROMETHEUS_METRICS_ENABLED` | Enable `/metrics` (default: true) |
| `COMPLETENESS_THRESHOLD` | Clarification score threshold (default: 0.75) |
| `MAX_CLARIFICATION_ROUNDS` | Max clarification rounds (default: 3) |

### Frontend env vars (`apps/web/.env.local`)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | FastAPI base URL (default: `http://localhost:8000`) |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase Web API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Firebase Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Firebase messaging sender |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase app ID |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry DSN for browser error tracking |

---

## 12. Test Strategy

### Backend
- **Unit tests** for agents: mocked LLM clients, no network. Run with `pytest agents/`.
- **Integration tests** for API: real Redis + Firestore emulator via `docker-compose.test.yml`. Run with `pytest apps/api/tests/`.
- **Linting**: `ruff check .` (configured in `pyproject.toml`).
- **Type checking**: `mypy src/` from `apps/api/`.
- CI pipelines: `.github/workflows/ci-api.yml`, `ci-agents.yml`, `ci-mcp-servers.yml`.

### Frontend
- **Unit/component tests**: Vitest + React Testing Library. `npm test` from `apps/web/`.
- **E2E tests**: Playwright (`apps/web/e2e/`). `npm run test:e2e`.
- **Type checking**: `npm run typecheck` (`tsc --noEmit`).
- **Linting**: `npm run lint` (ESLint with `@typescript-eslint` + `eslint-plugin-react-hooks`).
- CI pipeline: `.github/workflows/ci-web.yml`.
- Never test implementation details — test user-visible behaviour and integration with the store/query layer.
