# Career Roadmap AI

An AI-powered career coaching platform that generates personalized, end-to-end career roadmaps. Users describe their goals in natural language; a multi-agent system analyses their profile, maps skill gaps against live market data, and produces a structured learning and networking plan.

---

## Monorepo structure

```
career-roadmap-ai/
├── agents/                     # Standalone Python library — agentic framework
│   └── src/agents/
│       ├── contracts/          # Public API surface (only part imported by apps/api)
│       ├── core/               # BaseAgent, AgentRegistry, message-bus protocols
│       ├── bus/                # Celery tasks, Redis pub/sub publisher/subscriber
│       ├── orchestrator/       # LangGraph MasterOrchestrator + clarification engine
│       ├── cv_analysis/        # Specialist agent
│       ├── gap_analysis/       # Specialist agent
│       ├── market_intelligence/# Specialist agent
│       ├── roadmap_generation/ # Specialist agent
│       ├── learning_resources/ # Specialist agent
│       ├── coach/              # AI coaching agent
│       └── ...
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── src/
│   │   │   ├── config.py
│   │   │   ├── main.py
│   │   │   ├── core/           # Auth, exceptions, middleware, health
│   │   │   ├── session/        # Redis-backed session layer
│   │   │   ├── endpoints/v1/   # HTTP controllers
│   │   │   ├── observability/  # Prometheus, Sentry, OTel tracing
│   │   │   ├── streaming/      # SSE response helper
│   │   │   └── tasks/          # Celery worker entry-point
│   │   ├── observability/      # Docker configs for Tempo/Prometheus/Loki/Grafana
│   │   ├── docker-compose.dev.yml
│   │   └── pyproject.toml
│   └── web/                    # Next.js 16 frontend
│       └── src/
│           ├── app/            # App Router pages
│           ├── components/
│           ├── hooks/
│           ├── lib/api/        # Typed Axios API clients
│           ├── providers/      # Auth, Query, Theme providers
│           ├── store/          # Zustand stores
│           └── types/
├── mcp-servers/                # Model Context Protocol tool servers
│   ├── job-board/
│   ├── salary-benchmark/
│   ├── course-catalogue/
│   ├── github-trends/
│   ├── industry-news/
│   ├── social-signals/
│   └── calendar/
├── packages/
│   ├── shared-types/           # Shared TypeScript types
│   └── ui/                     # Shared React component library
├── infrastructure/             # Terraform + Docker production configs
├── documentation/
└── Makefile                    # Developer task runner
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind CSS v4, shadcn/ui |
| State | Zustand, TanStack Query |
| Auth | Firebase Auth (client-side; ID tokens verified server-side) |
| Backend | FastAPI, Python 3.12, Poetry 2 |
| User data | Firebase Firestore |
| Sessions | Redis 7 (24h sliding TTL, single JSON doc per user) |
| Task queue | Celery 5 + Redis broker |
| AI framework | LangGraph, LangChain, Anthropic claude-sonnet-4-6 |
| Observability | Prometheus, Grafana Tempo (OTel traces), Loki (logs), Grafana |
| Error tracking | Sentry |

---

## Architecture overview

### Inter-agent message bus

```
Client
  │  POST /api/v1/orchestrator/generate
  ▼
FastAPI (apps/api)
  │  dispatch via Celery (Redis broker, agents.priority queue)
  ▼
agents.bus.tasks.run_orchestration   ← Celery worker
  │
  ▼
MasterOrchestrator (LangGraph StateGraph)
  ├─ parse_intent
  ├─ score_completeness  ──── < 0.75? ──► return clarification_questions (END)
  ├─ build_dag
  ├─ dispatch_and_collect  ── asyncio.gather across specialist agents
  ├─ validate
  └─ synthesize
        │ emit AgentEvents via Redis pub/sub
        ▼
  agent_events:{user_id}:{session_id}
        │
        ▼
  GET /api/v1/stream/{session_id}  ← SSE bridge (apps/api)
        │
        ▼
      Client (EventSource)
```

**Coupling rule:** `apps/api` imports only from `agents.contracts`. The agents package never imports from `apps/api`. The sole conversion point is `_to_profile_snapshot()` in `orchestrator_controller.py`.

### Session layer

All conversational state lives in Redis (`session:{firebase_uid}`). The `SessionManager` is injected via FastAPI dependency; nothing touches Redis directly. Conversation history is capped at 100 turns; follow-up questions are capped at 3.

---

## Prerequisites

- Python 3.12+
- Poetry 2+
- Node.js 20+
- Docker Desktop

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/rogerjeasy/career-roadmap-ai.git
cd career-roadmap-ai
make install
```

`make install` runs `poetry install` for the API then installs `agents/` as an editable package into the same virtualenv.

### 2. Configure environment

```bash
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` and fill in the required values:

```env
# Firebase — get from Firebase Console → Project Settings
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
FIREBASE_WEB_API_KEY=AIzaSy...

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Redis & Celery (defaults work if you use docker compose)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### 3. Start infrastructure

```bash
make infra-up       # Postgres + Redis
```

### 4. Run the API

```bash
make dev            # uvicorn with --reload on :8000
```

### 5. Run the Celery worker (separate terminal)

```bash
make worker
```

### 6. Run the frontend

```bash
cd apps/web
npm install
npm run dev         # Next.js dev server on :3000
```

API docs (dev only): http://localhost:8000/docs

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Exchange Firebase ID token for session |
| `POST` | `/api/v1/auth/logout` | Invalidate session |
| `GET` | `/api/v1/users/me` | Current user profile |
| `GET` | `/api/v1/session` | Load current session |
| `POST` | `/api/v1/session/message` | Append conversation turn |
| `GET` | `/api/v1/session/profile` | Get profile context |
| `PATCH` | `/api/v1/session/profile` | Update profile context |
| `POST` | `/api/v1/session/clarification/reply` | Submit clarification answers |
| `DELETE` | `/api/v1/session` | Reset session |
| `POST` | `/api/v1/orchestrator/generate` | Trigger roadmap generation (async, returns `request_id`) |
| `GET` | `/api/v1/orchestrator/status/{request_id}` | Poll Celery task status |
| `GET` | `/api/v1/stream/{session_id}` | SSE stream of live agent events |
| `GET` | `/livez` | Liveness probe |
| `GET` | `/readyz` | Readiness probe |
| `GET` | `/metrics` | Prometheus metrics |

### Generation + streaming flow

```
1. POST /orchestrator/generate
   → { request_id, stream_channel, status: "queued" }

2. Open EventSource to GET /stream/{session_id}
   → receive AgentEvents as they are emitted

3. If CLARIFICATION_REQUIRED event arrives
   → surface questions to user
   → POST /session/clarification/reply with answers
   → POST /orchestrator/generate again (enriched profile auto-loaded from session)

4. ORCHESTRATION_COMPLETED carries the final roadmap in its payload
```

---

## Observability

### Always-on

- **Prometheus metrics** at `/metrics` — HTTP RED metrics (rate, errors, duration) + custom AI counters (`agent_invocations_total`, `llm_tokens_total`, `agent_duration_seconds`, `mcp_tool_calls_total`)
- **Structured JSON logs** via structlog (stdout)
- **Sentry** error tracking (set `SENTRY_DSN` in `.env`)

### Full observability stack (opt-in)

Starts Grafana Tempo (traces), Prometheus, Loki (logs), Promtail, and Grafana — all wired together with exemplar links from metrics to traces to logs.

```bash
make obs-up
```

Then enable trace export in `.env`:

```env
OTEL_TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

| Service | URL |
|---|---|
| Grafana (pre-built dashboard) | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| Tempo | http://localhost:3200 |
| Loki | http://localhost:3100 |

Stop the observability stack:

```bash
make obs-down
```

---

## Development commands

```bash
make install        # First-time setup (API venv + agents editable install)
make dev            # Infra up + API dev server
make worker         # Celery worker
make obs-up         # Optional: full observability stack
make obs-down       # Stop observability stack

make test           # All tests (API + agents)
make test-api       # API tests only
make test-agents    # Agents tests only

make lint           # Ruff check + format check
make format         # Auto-format (ruff format)

make infra-up       # Start Postgres + Redis
make infra-down     # Stop Postgres + Redis
make clean          # Remove __pycache__ and build artefacts
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

2. Register at import time in `agents/src/agents/__init__.py`:

```python
from agents.core.agent_registry import registry
from agents.my_domain.agent import MyAgent

registry.register(MyAgent())
```

3. Add `AgentType.MY_AGENT` to the `AgentType` enum in `agents/src/agents/contracts/tasks.py`.

4. Wire it into a DAG template in `agents/src/agents/orchestrator/task_planner.py`.

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | | `development` | `development` / `staging` / `production` |
| `DEBUG` | | `false` | Enables `/docs` and `/redoc` |
| `FIREBASE_PROJECT_ID` | Yes | — | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | Yes* | — | Path to service account JSON |
| `FIREBASE_CREDENTIALS_JSON` | Yes* | — | Inline JSON (CI / cloud) |
| `FIREBASE_WEB_API_KEY` | Yes | — | Firebase Web API Key |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `REDIS_URL` | Yes | — | Redis connection URL |
| `CELERY_BROKER_URL` | Yes | — | Celery broker (Redis) |
| `CELERY_RESULT_BACKEND` | Yes | — | Celery result backend (Redis) |
| `DATABASE_URL` | | — | Postgres URL (reserved for future use) |
| `SENTRY_DSN` | | — | Sentry DSN |
| `OTEL_TRACING_ENABLED` | | `false` | Enable OTel trace export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | | — | OTLP gRPC endpoint (e.g. `http://localhost:4317`) |
| `RATE_LIMIT_PER_MINUTE` | | `60` | Global API rate limit |

*One of `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` is required.
