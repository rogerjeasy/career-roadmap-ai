# Career Roadmap AI

An AI-powered career coaching platform that generates personalised, end-to-end career roadmaps. Users describe their goals in natural language; a multi-agent LangGraph pipeline analyses their profile, maps skill gaps against live market data, and produces a structured week-by-week learning and networking plan.

All traffic enters through a **Kong API Gateway** that handles routing, rate limiting, CORS, and distributed tracing before requests reach the application layer.

---

## Monorepo structure

```
career-roadmap-ai/
├── agents/                     # Standalone Python package — agentic framework
│   └── src/agents/
│       ├── contracts/          # Public API surface (only part imported by apps/api)
│       ├── core/               # BaseAgent, AgentRegistry, message-bus protocols
│       ├── bus/                # Celery tasks, Redis pub/sub publisher/subscriber
│       ├── orchestrator/       # LangGraph MasterOrchestrator + clarification engine
│       ├── coach/              # AI coaching specialist agent
│       ├── opportunity/        # Opportunity matching specialist agent
│       └── rag/                # RAG pipeline (Pinecone + Voyage AI + Cloudinary)
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── core/           # Auth, exceptions, middleware, logging
│   │   │   ├── domains/        # user, cv, roadmap, market, opportunities …
│   │   │   ├── session/        # Redis-backed session layer
│   │   │   ├── endpoints/v1/   # HTTP controllers
│   │   │   └── observability/  # Prometheus, Sentry, OTel setup
│   │   ├── kong/
│   │   │   └── kong.dev.yml    # Kong declarative config (dev, DB-less)
│   │   ├── observability/      # Grafana/Prometheus/Loki/Tempo configs + dashboards
│   │   ├── docker-compose.dev.yml
│   │   └── pyproject.toml
│   └── web/                    # Next.js 16 frontend
│       └── src/
│           ├── app/            # App Router pages
│           ├── components/
│           ├── hooks/
│           ├── lib/api/        # Typed Axios API clients
│           ├── providers/
│           ├── store/          # Zustand stores
│           └── types/
├── mcp-servers/                # Model Context Protocol JSON-RPC 2.0 tool servers
│   ├── job-board/              # :3001  LinkedIn, Indeed, Glassdoor, jobs.ch
│   ├── course-catalogue/       # :3002  Coursera, Udemy, edX, YouTube, O'Reilly
│   ├── github-trends/          # :3003  Trending repos + language stats
│   ├── salary-benchmark/       # :3004  Salary data by role/location
│   ├── social-signals/         # :3005  HackerNews, Reddit, Twitter/X
│   ├── calendar/               # :3006  Google Calendar + Outlook
│   └── industry-news/          # :3007  Tech news aggregation
├── infrastructure/
│   ├── kong/
│   │   ├── kong.yml            # Production Kong config (deck-managed)
│   │   └── deck.env.example    # Variables for deck sync
│   ├── terraform/
│   │   ├── modules/
│   │   │   ├── api-gateway/    # Kong on Azure Container Apps
│   │   │   ├── networking/
│   │   │   ├── database/
│   │   │   ├── redis/
│   │   │   ├── storage/
│   │   │   └── container-apps/
│   │   └── environments/
│   │       ├── production/
│   │       └── staging/
│   └── docker/                 # Production Dockerfiles
├── packages/
│   ├── shared-types/           # Shared TypeScript types
│   └── ui/                     # Shared shadcn/ui component library
├── documentation/              # HTML architecture diagrams, ADRs
└── Makefile                    # Developer task runner (run `make help`)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind CSS v4, shadcn/ui |
| State | Zustand, TanStack Query v5 |
| Auth | Firebase Auth — ID tokens verified server-side via Firebase Admin SDK |
| **API Gateway** | **Kong OSS 3.8** — routing, rate limiting, CORS, OTel root spans |
| Backend | FastAPI, Python 3.12, Poetry 2 |
| User data | Firebase Firestore |
| Relational DB | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Sessions | Redis 7 — 24h sliding TTL, one JSON document per user |
| Task queue | Celery 5 + Redis broker |
| MCP tools | 7 FastAPI JSON-RPC 2.0 servers (each with own Redis cache + rate limiter) |
| AI framework | LangGraph, LangChain, Anthropic claude-sonnet-4-6 |
| RAG | Pinecone (vectors), Voyage AI (embeddings), Cloudinary (document storage) |
| Metrics | Prometheus — HTTP RED metrics + custom AI counters |
| Tracing | OpenTelemetry → Grafana Tempo (OTLP gRPC) |
| Logs | structlog (JSON) → Promtail → Loki |
| Dashboards | Grafana (pre-built: API dashboard + Kong gateway dashboard) |
| Error tracking | Sentry |
| Infrastructure | Azure Container Apps, Terraform |

---

## Architecture overview

### Request flow

```
Browser (Next.js :3000)
        │
        │  rewrites() in next.config.ts
        │  dev:  http://localhost:8080
        │  prod: https://<kong-fqdn>
        ▼
┌──────────────────────────────────────────────────────────┐
│  Kong API Gateway                                        │
│  • CORS (primary handler)                                │
│  • Rate limiting — Redis DB 9, per IP                    │
│  • Request size limit (10 MB)                            │
│  • Security headers (HSTS, X-Frame-Options, CSP hints …) │
│  • OTel root span → Grafana Tempo                        │
│  • Prometheus metrics → Grafana                          │
└──────────┬──────────────────┬───────────────────────────┘
           │ /api/v1/**       │ /mcp/<name>/**
           │ /auth/**         │ strip_path: true
           │ /stream/**       │
           ▼                  ▼
   ┌──────────────┐   ┌────────────────────────────────────┐
   │  FastAPI     │   │  MCP Tool Servers (JSON-RPC 2.0)   │
   │  :8000       │   │                                    │
   │              │   │  job-board        :3001             │
   │  Firebase    │   │  course-catalogue :3002             │
   │  auth        │   │  github-trends    :3003             │
   │  Pydantic    │   │  salary-benchmark :3004             │
   │  validation  │   │  social-signals   :3005             │
   │  business    │   │  calendar         :3006             │
   │  logic       │   │  industry-news    :3007             │
   └──────┬───────┘   └────────────────────────────────────┘
          │
          │ Celery task (Redis broker)
          ▼
   ┌──────────────────────────────────────────────────────┐
   │  LangGraph MasterOrchestrator (Celery worker)        │
   │                                                      │
   │  parse_intent → score_completeness                   │
   │    └─ < 0.75 → return clarification questions        │
   │  build_dag → dispatch_and_collect (asyncio.gather)   │
   │    ├─ CVAnalysisAgent                                │
   │    ├─ GapAnalysisAgent                               │
   │    ├─ MarketIntelligenceAgent  ──► MCP servers       │
   │    ├─ RoadmapGenerationAgent                         │
   │    └─ LearningResourcesAgent  ──► MCP servers        │
   │  validate → synthesize                               │
   │    └─ emit AgentEvents via Redis pub/sub             │
   └──────────────────────────────────────────────────────┘
          │ Redis pub/sub  agent_events:{uid}:{session_id}
          ▼
   GET /stream/{session_id}  ← SSE bridge (FastAPI)
          │
          ▼
   EventSource in browser
```

**Coupling rule:** `apps/api` imports only from `agents.contracts`. The agents package never imports from `apps/api`.

### Session layer

All conversational state lives in Redis (`session:{firebase_uid}`). Injected via FastAPI `Depends`; nothing touches Redis directly in controllers. Conversation history is capped at 100 turns; clarification rounds at 3.

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.12 |
| Poetry | 2.0 |
| Node.js | 20 |
| Docker Desktop | latest |
| `deck` CLI *(production Kong management only)* | 2.x |

### Windows notes

- Use **`curl.exe`** (not `curl`) in PowerShell — `curl` is aliased to `Invoke-WebRequest` and doesn't show raw response headers.
- The Celery worker automatically uses `--pool=solo` on Windows (the Makefile detects `OS=Windows_NT`). No POSIX semaphores are required and all tasks run correctly.
- `npm` targets in the Makefile automatically use `npm.cmd` on Windows.
- `CORS_ORIGINS` in `.env` must be a JSON array: `CORS_ORIGINS=["http://localhost:3000"]` — plain strings fail pydantic-settings v2 parsing.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/rogerjeasy/career-roadmap-ai.git
cd career-roadmap-ai
make install          # poetry install + agents editable install + npm install
```

### 2. Configure the backend

```bash
cp apps/api/.env.example apps/api/.env
```

Fill in `apps/api/.env`:

```env
# Firebase — Firebase Console → Project Settings
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
FIREBASE_WEB_API_KEY=...

# LLM
ANTHROPIC_API_KEY=...

# Redis & Celery (defaults work with docker compose)
REDIS_URL= 
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### 3. Configure the frontend

```bash
cp apps/web/.env.local.example apps/web/.env.local
```

Fill in `apps/web/.env.local`:

```env
# API gateway URL — Kong proxy (dev: localhost:8080)
NEXT_PUBLIC_API_URL=http://localhost:8080

# Firebase Web SDK
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
```

### 4. Start infrastructure + API gateway

**Option A — everything at once (recommended)**

```bash
make dev-full
# Starts: Postgres · Redis · Kong · Tempo · Prometheus · Loki · Grafana · FastAPI
```

**Option B — minimal (Postgres + Redis + Kong only)**

```bash
make gateway-up       # Postgres + Redis + Kong on :8080
make dev              # FastAPI dev server on :8000
```

**Option C — no gateway (direct to FastAPI)**

```bash
make infra-up         # Postgres + Redis only
make dev              # FastAPI on :8000
```

### 5. Run the Celery worker (separate terminal)

```bash
make worker
```

### 6. Run the frontend (separate terminal)

```bash
make web-dev          # Next.js on :3000, proxies to Kong at :8080
```

### 7. Run database migrations

```bash
make db-migrate
```

---

## Port reference

| Service | Dev port | Notes |
|---|---|---|
| Next.js | :3000 | Frontend dev server |
| **Kong proxy (HTTP)** | **:8080** | **Single entry point for all API calls** |
| Kong proxy (HTTPS) | :8443 | Self-signed cert in dev |
| Kong Admin API | :8001 | `127.0.0.1` only — `make gateway-admin` |
| FastAPI | :8000 | Still reachable directly for quick `curl` |
| MCP: job-board | :3001 | Local process (outside Docker) |
| MCP: course-catalogue | :3002 | Local process (outside Docker) |
| MCP: github-trends | :3003 | Local process (outside Docker) |
| MCP: salary-benchmark | :3004 | Local process (outside Docker) |
| MCP: social-signals | :3005 | Local process (outside Docker) |
| MCP: calendar | :3006 | Local process (outside Docker) |
| MCP: industry-news | :3007 | Local process (outside Docker) |
| Grafana | :3300 | Password-free in dev — dashboards auto-provisioned |
| Prometheus | :9090 | |
| Tempo | :3200 | |
| Loki | :3100 | |
| PostgreSQL | :5432 | |
| Redis | :6379 | |

---

## API endpoints

All endpoints are exposed **through Kong** at `http://localhost:8080` in dev. FastAPI is still reachable directly at `:8000` but CORS is only fully configured at the gateway.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Exchange Firebase ID token for session |
| `POST` | `/auth/logout` | Invalidate session |
| `GET` | `/api/v1/users/me` | Current user profile |
| `GET` | `/api/v1/session` | Load current session |
| `POST` | `/api/v1/session/message` | Append conversation turn |
| `GET` | `/api/v1/session/profile` | Get profile context |
| `PATCH` | `/api/v1/session/profile` | Update profile context |
| `POST` | `/api/v1/session/clarification/reply` | Submit clarification answers |
| `DELETE` | `/api/v1/session` | Reset session |
| `POST` | `/api/v1/orchestrator/generate` | Trigger roadmap generation (async, returns `request_id`) |
| `GET` | `/api/v1/orchestrator/status/{request_id}` | Poll Celery task status |
| `GET` | `/stream/{session_id}` | SSE stream of live agent events |
| `POST` | `/mcp/{server}` | MCP tool call (JSON-RPC 2.0 body) |
| `GET` | `/livez` | Kong → FastAPI liveness probe |
| `GET` | `/readyz` | Kong → FastAPI readiness probe |

### Generation + streaming flow

```
1. POST /api/v1/orchestrator/generate
   → { request_id, stream_channel, status: "queued" }

2. Open EventSource to GET /stream/{session_id}
   → receive AgentEvents as they are emitted
   (Kong route has 1h timeout + response_buffering: false)

3. If CLARIFICATION_REQUIRED event arrives
   → surface questions to the user
   → POST /api/v1/session/clarification/reply with answers
   → POST /api/v1/orchestrator/generate again
     (enriched profile is auto-loaded from session)

4. ORCHESTRATION_COMPLETED carries the final roadmap in its payload
```

---

## Kong API Gateway

### What Kong handles (vs. FastAPI)

| Concern | Kong (infrastructure layer) | FastAPI (application layer) |
|---|---|---|
| TLS termination | Yes — Azure ingress in production | — |
| Rate limiting | Global per-IP; per-route overrides | Per-user domain limits |
| CORS | Primary handler | Defense-in-depth fallback |
| Routing | All 8 services unified | Single-app routing |
| OTel tracing | Root span (gateway entry) | Child spans (business logic) |
| Auth | — (Firebase RS256 not natively verifiable) | Firebase Admin SDK |
| Pydantic validation | — | Full schema validation |

### Dev workflow

```bash
make gateway-up       # Start Kong (DB-less, reads kong/kong.dev.yml)
make gateway-reload   # Pick up config changes without restarting all services
make gateway-logs     # Tail Kong access + error logs
make gateway-admin    # curl localhost:8001/routes (smoke test Admin API)
```

Kong config lives in `apps/api/kong/kong.dev.yml`. Edit the file and run `make gateway-reload` — no Docker rebuild needed.

### Production config (deck)

Production routes and plugins are managed with [deck](https://docs.konghq.com/deck/), Kong's declarative config CLI:

```bash
# 1. Copy and populate the env file
cp infrastructure/kong/deck.env.example infrastructure/kong/.env.production

# 2. Diff local config against live cluster (dry run)
make deck-diff

# 3. Apply changes
make deck-sync
```

The production config is at `infrastructure/kong/kong.yml`. `deck sync` is run as a CI/CD step after `terraform apply`.

---

## Observability

### Always-on

- **Prometheus metrics** at `/metrics` on FastAPI — HTTP RED metrics + custom AI counters (`agent_invocations_total`, `llm_tokens_total`, `mcp_tool_calls_total`, `agent_duration_seconds`)
- **Kong metrics** at `localhost:8001/metrics` — gateway-level request rate, latency percentiles, upstream health, bandwidth
- **Structured JSON logs** via structlog (stdout → Promtail → Loki in the full stack)
- **Sentry** error tracking — set `SENTRY_DSN` in `.env`

### Full observability stack (opt-in)

```bash
make obs-up             # Observability only (no gateway)
make gateway-obs-up     # Kong + observability together (recommended)
```

Then enable trace export in `apps/api/.env`:

```env
OTEL_TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

| Service | URL | What's in it |
|---|---|---|
| Grafana | http://localhost:3300 | Two pre-built dashboards (see below) |
| Prometheus | http://localhost:9090 | Scrapes FastAPI + Kong + Redis + Postgres |
| Tempo | http://localhost:3200 | OTel traces — gateway root spans + FastAPI child spans |
| Loki | http://localhost:3100 | Structured logs from all containers |

**Pre-built Grafana dashboards:**

| Dashboard | UID | Contents |
|---|---|---|
| Career Roadmap API | `career-roadmap-api` | HTTP RED metrics, agent durations, LLM token usage, Celery queue depth |
| Kong API Gateway | `kong-gateway` | Request rate by service, error rate, p50/p95/p99 latency (proxy vs upstream), upstream health table, bandwidth, rate-limit hit rate |

Both dashboards are provisioned automatically — no import needed.

```bash
make gateway-obs-down   # Stop Kong + observability
make obs-down           # Stop observability only
```

---

## Development commands

```bash
# ── Setup ──────────────────────────────────────────────────────────────
make install            # Full first-time setup (API + agents + frontend)
make install-api        # Python/Poetry install only
make install-web        # npm install only

# ── Development ────────────────────────────────────────────────────────
make dev-full           # Everything: infra + Kong + observability + FastAPI
make dev                # Core infra + FastAPI (no gateway, no obs stack)
make web-dev            # Next.js dev server (:3000, proxies to Kong :8080)
make worker             # Celery worker

# ── Infrastructure ─────────────────────────────────────────────────────
make infra-up           # Postgres + Redis
make infra-down         # Stop all services (all profiles)

# ── API Gateway ────────────────────────────────────────────────────────
make gateway-up         # Start Kong (DB-less)
make gateway-down       # Stop Kong container
make gateway-reload     # Reload kong.dev.yml without restarting
make gateway-logs       # Tail Kong logs
make gateway-admin      # Smoke-test Kong Admin API (:8001/routes)
make gateway-obs-up     # Kong + full observability stack
make gateway-obs-down   # Stop Kong + observability

# ── Observability ──────────────────────────────────────────────────────
make obs-up             # Tempo + Prometheus + Loki + Grafana
make obs-down           # Stop observability stack

# ── Database ───────────────────────────────────────────────────────────
make db-migrate         # Alembic upgrade head
make db-rollback        # Alembic downgrade -1

# ── Production Kong (deck) ─────────────────────────────────────────────
make deck-diff          # Dry-run diff against live Kong cluster
make deck-sync          # Push infrastructure/kong/kong.yml to production

# ── Testing ────────────────────────────────────────────────────────────
make test               # All tests (API + agents + frontend)
make test-api           # API tests (pytest)
make test-agents        # Agents tests (pytest)
make test-web           # Frontend unit/component tests (Vitest)
make test-e2e           # Playwright end-to-end tests

# ── Code quality ───────────────────────────────────────────────────────
make lint               # Ruff check + format check + ESLint
make format             # Auto-format (ruff format)
make web-typecheck      # TypeScript strict-mode check (tsc --noEmit)
make web-build          # Production Next.js build

# ── Cleanup ────────────────────────────────────────────────────────────
make clean              # Remove __pycache__, .next, *.egg-info artefacts
make help               # List all available targets
```

---

## Adding a specialist agent

1. Create `agents/src/agents/<domain>/agent.py` extending `BaseAgent`:

```python
from agents.core.base_agent import AgentContext, BaseAgent
from agents.contracts.tasks import AgentType

class MyAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.MY_AGENT

    async def _execute(self, context: AgentContext) -> dict:
        ...
        return {"result": ...}
```

2. Register in `agents/src/agents/__init__.py`:

```python
from agents.core.agent_registry import registry
from agents.my_domain.agent import MyAgent

registry.register(MyAgent())
```

3. Add `AgentType.MY_AGENT` to the enum in `agents/src/agents/contracts/tasks.py`.

4. Wire it into a DAG template in `agents/src/agents/orchestrator/task_planner.py`.

---

## Adding an MCP server

1. Scaffold under `mcp-servers/<name>/` following an existing server (e.g. `calendar/`)
2. Choose the next available port (current highest: `3007`)
3. Implement `server.py` with `/livez`, `/readyz`, `/metrics`, and `POST /` JSON-RPC dispatcher
4. Add the new upstream and route to **both** config files:
   - `apps/api/kong/kong.dev.yml` (dev)
   - `infrastructure/kong/kong.yml` (production)
5. Run `make gateway-reload` to apply without restarting

---

## Environment variables reference

### Backend (`apps/api/.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | | `development` | `development` / `staging` / `production` |
| `DEBUG` | | `false` | Enables `/docs` and `/redoc` |
| `FIREBASE_PROJECT_ID` | Yes | — | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | Yes* | — | Path to service account JSON |
| `FIREBASE_CREDENTIALS_JSON` | Yes* | — | Inline JSON (CI / cloud) |
| `FIREBASE_WEB_API_KEY` | Yes | — | Firebase Web API key |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `REDIS_URL` | Yes | — | Redis DSN (app sessions, Celery) |
| `CELERY_BROKER_URL` | Yes | — | Redis DSN for Celery broker |
| `CELERY_RESULT_BACKEND` | Yes | — | Redis DSN for Celery results |
| `DATABASE_URL` | | — | PostgreSQL async DSN |
| `SENTRY_DSN` | | — | Sentry DSN |
| `OTEL_TRACING_ENABLED` | | `false` | Enable OTel trace export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | | — | OTLP gRPC endpoint (e.g. `http://localhost:4317`) |
| `RATE_LIMIT_PER_MINUTE` | | `60` | App-level rate limit (Kong also applies one) |

*One of `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` is required.

### Frontend (`apps/web/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Kong proxy URL — `http://localhost:8080` in dev |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Yes | Firebase Web API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Yes | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Yes | Firebase Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Yes | Firebase messaging sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Yes | Firebase app ID |
| `NEXT_PUBLIC_SENTRY_DSN` | | Sentry DSN for browser error tracking |
