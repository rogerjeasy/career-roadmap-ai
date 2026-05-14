# End-to-End Test Guide

Step-by-step process to verify the full stack: Kong API Gateway, FastAPI backend, Celery worker, Next.js frontend, and the complete observability pipeline (Prometheus, Grafana, Tempo, Loki).

---

## Windows note — `curl` vs `curl.exe`

PowerShell aliases `curl` to `Invoke-WebRequest`. Use `curl.exe` everywhere in this guide to get real curl output with proper headers and exit codes:

```powershell
curl.exe -v http://localhost:8080/livez
```

---

## Prerequisites

Confirm the following are installed before starting:

| Tool | Check |
|---|---|
| Docker Desktop (running) | `docker info` |
| Python 3.12+ | `python --version` |
| Poetry 2+ | `poetry --version` |
| Node.js 20+ | `node --version` |
| Make | `make --version` |

If you haven't run `make install` yet:

```bash
make install
```

---

## Step 1 — Configure environment files

### Backend

```bash
cp apps/api/.env.example apps/api/.env
```

Open `apps/api/.env` and fill in the required values:

```env
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
FIREBASE_WEB_API_KEY=...
ANTHROPIC_API_KEY=...

# Enable OTel so traces flow into Tempo
OTEL_TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Key notes:
- `CORS_ORIGINS` must be a **JSON array**: `CORS_ORIGINS=["http://localhost:3000"]`
- `RERANKER_TOP_N` must be an integer if set — default `20` is pre-filled in `.env.example`
- Leave MCP URL vars blank to use `StubMCPClient` (safe for local dev without running MCP servers)
- To activate live data from MCP servers, add these after starting them in Step 5a:

```env
MCP_JOB_BOARD_URL=http://localhost:3001
MCP_COURSE_CATALOG_URL=http://localhost:3002
MCP_SALARY_BENCHMARK_URL=http://localhost:3003
MCP_GITHUB_TRENDS_URL=http://localhost:3004
MCP_SOCIAL_SIGNALS_URL=http://localhost:3005
MCP_INDUSTRY_NEWS_URL=http://localhost:3007
```

### Frontend

```bash
cp apps/web/.env.example apps/web/.env.local
```

Open `apps/web/.env.local` and fill in the Firebase Web SDK values:

```env
# Must point to Kong — not FastAPI directly
NEXT_PUBLIC_API_URL=http://localhost:8080

NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=000000000000
NEXT_PUBLIC_FIREBASE_APP_ID=1:000000000000:web:abc123
```

> **Important:** `NEXT_PUBLIC_API_URL` must be `http://localhost:8080` (Kong), not `:8000` (FastAPI). All API calls from the browser go through Kong.

---

## Step 2 — Start all infrastructure

One command starts PostgreSQL, Redis, Kong API Gateway, and the full observability stack (Prometheus, Grafana, Tempo, Loki, Promtail):

```bash
make gateway-obs-up
```

Wait ~30 seconds, then verify all containers are healthy:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep crai
```

Expected output:

```
crai-kong               Up X seconds (healthy)
crai-postgres           Up X seconds (healthy)
crai-redis              Up X seconds (healthy)
crai-tempo              Up X seconds (healthy)
crai-prometheus         Up X seconds (healthy)
crai-loki               Up X seconds (healthy)
crai-grafana            Up X seconds
crai-promtail           Up X seconds
crai-redis-exporter     Up X seconds
crai-postgres-exporter  Up X seconds
```

---

## Step 3 — Run database migrations

```bash
make db-migrate
```

You should see Alembic apply all pending migrations without errors.

---

## Step 4 — Start the FastAPI backend

Open a dedicated terminal:

```bash
make dev
```

FastAPI is ready when the terminal shows:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> FastAPI runs on `:8000` internally. All external traffic reaches it through Kong on `:8080`.

---

## Step 5 — Start the Celery worker

Open a second terminal:

```bash
make worker
```

The Makefile automatically selects the correct pool:
- **Windows**: `--pool=solo` (no POSIX semaphores required)
- **Linux / macOS**: `--pool=prefork --concurrency=4`

The worker is needed for roadmap generation (async pipeline). For login/register testing it is optional, but start it now to test the full flow later.

**Stopping the worker:** press `Ctrl+C` in its terminal. The worker runs in the foreground — there is no background process to hunt down.

**Restarting after `infra-down` / `infra-up`:** Redis persists its data to a Docker volume, so old Celery tasks survive the container restart and replay when the worker reconnects. Always purge before starting a fresh session:

```bash
make worker-purge   # discard pending tasks from the queues
make worker         # start clean
```

If you want a harder reset (also clears task results and any orphaned keys):

```bash
make worker-flush   # flushes Redis DB1 (broker) + DB2 (results) entirely
make worker
```

---

## Step 5a — Start MCP servers (optional — activates live data)

MCP servers supply real-world data to agents: job postings, course catalogues, salary ranges, GitHub trends, social signals, and industry news. Without them the agents use stub data tagged `source: "stub"`.

Open a new terminal and run:

```bash
make mcp-start
```

This starts all 6 servers in the background (logs written to `logs/mcp/<name>.log`) and polls each `/livez` endpoint until they are all healthy. Expected output:

```
Starting MCP servers...
------------------------------------------------------------
  job-board              port 3001   PID ...   log: logs/mcp/job-board.log
  course-catalogue       port 3002   PID ...   log: logs/mcp/course-catalogue.log
  salary-benchmark       port 3003   PID ...   log: logs/mcp/salary-benchmark.log
  github-trends          port 3004   PID ...   log: logs/mcp/github-trends.log
  social-signals         port 3005   PID ...   log: logs/mcp/social-signals.log
  industry-news          port 3007   PID ...   log: logs/mcp/industry-news.log
------------------------------------------------------------

Waiting for /livez on all servers (30s timeout)...
  job-board              UP
  course-catalogue       UP
  salary-benchmark       UP
  github-trends          UP
  social-signals         UP
  industry-news          UP
```

After all servers are UP, add the MCP URL vars to `apps/api/.env` (see Step 1) and restart FastAPI so the agents pick them up.

### Managing individual servers

Every server has its own stop, restart, and log-tail command:

```bash
# Stop one server
make mcp-stop-course-catalogue

# Restart one server (stop full process tree → start → health check)
make mcp-restart-course-catalogue

# Tail its log live (Ctrl+C to stop)
make mcp-logs-course-catalogue
```

Same pattern works for all six: `job-board`, `course-catalogue`, `salary-benchmark`, `github-trends`, `social-signals`, `industry-news`.

### After code changes

When you edit a server's Python files, the reload watcher inside uvicorn picks them up automatically. If that fails (stale `.pyc` files, zombie reloader process), restart the server properly:

```bash
make mcp-restart-course-catalogue   # single server
make mcp-restart                    # all servers at once
```

This kills the **entire process tree** (reloader parent + worker child) before relaunching, so no stale code survives.

> **Data without API keys:** course catalogue (100+ curated courses + Coursera public API), salary benchmarks (curated CH/DE/US dataset), GitHub trends (60 req/hr unauthenticated), industry news (10 RSS feeds), HackerNews, Reddit, and Dev.to signals all work with zero API keys. See `apps/api/.env.example` for optional keys that unlock additional sources.

---

## Step 6 — Start the frontend

Open a third terminal:

```bash
make web-dev
```

Next.js is ready when you see:

```
▲ Next.js 16.x.x
- Local: http://localhost:3000
```

---

## Step 7 — Verify Kong is routing correctly

### 7a — Check all routes are loaded

```bash
make gateway-admin
```

You should see JSON listing all configured routes: `api-v1`, `auth`, `stream-sse`, `health`, `mcp-job-board-route`, `mcp-calendar-route`, etc.

If Kong is not running you will see a helpful message — run `make gateway-obs-up` first.

### 7b — Hit a live endpoint through Kong

**Linux / macOS:**
```bash
curl -v http://localhost:8080/livez
```

**Windows (PowerShell):**
```powershell
curl.exe -v http://localhost:8080/livez
```

A correct response looks like:

```
< HTTP/1.1 200 OK
< X-Kong-Upstream-Latency: 3
< X-Kong-Proxy-Latency: 1
< X-Content-Type-Options: nosniff
< X-Frame-Options: DENY
...
{"status": "alive"}
```

The `X-Kong-*` headers confirm the request passed through Kong. The security headers (`X-Content-Type-Options`, `X-Frame-Options`) confirm the `response-transformer` plugin is active.

> Note: the endpoint is `/livez` (with a `z`), not `/live`. A 404 from FastAPI means Kong routing works but you used the wrong path.

### 7c — Confirm Prometheus is scraping Kong

Open **http://localhost:9090/targets**

All scrape targets should show **State: UP**:

| Job | Target |
|---|---|
| `career-roadmap-api` | `host.docker.internal:8000` |
| `kong` | `kong:8001` |
| `redis` | `redis-exporter:9121` |
| `postgres` | `postgres-exporter:9187` |

---

## Step 8 — Test register and login in the browser

Open **http://localhost:3000**

### Register a new account

1. Navigate to the Register page
2. Fill in name, email, and password
3. Submit the form

**What to verify in browser DevTools → Network tab:**
- The request URL is `http://localhost:8080/auth/register` (Kong), **not** `http://localhost:8000`
- The response headers include `X-Kong-Proxy-Latency` and `X-Kong-Upstream-Latency`
- HTTP status is `201` or `200`

### Log in

1. Navigate to the Login page
2. Enter the credentials you just registered
3. Submit

**What to verify:**
- Request goes to `http://localhost:8080/auth/login`
- A Firebase ID token is returned and stored in the browser
- You are redirected to the dashboard

---

## Step 9 — Verify the observability pipeline

### 9a — Grafana dashboards

Open **http://localhost:3300** (no login required in dev)

Navigate to **Dashboards**. Two pre-built dashboards are auto-provisioned:

#### Kong API Gateway dashboard (`uid: kong-gateway`)

| Panel | What you should see |
|---|---|
| Request Rate | A small spike from your login/register requests |
| Error Rate | `0%` if auth succeeded |
| P99 Proxy Latency | Milliseconds — Kong overhead only |
| P99 Upstream Latency | Time inside FastAPI |
| Upstream Target Health | `fastapi.upstream` row showing `Healthy` |

#### Career Roadmap API dashboard (`uid: career-roadmap-api`)

| Panel | What you should see |
|---|---|
| HTTP request rate | Requests to `/auth/*` visible |
| Error rate | `0%` |
| Response time | Latency for Firebase token verification |

> Grafana polls Prometheus every 15 seconds. If panels are empty, wait 15–30 seconds and refresh.

### 9b — Distributed traces in Tempo

1. In Grafana, go to **Explore** (compass icon in the left sidebar)
2. Select the **Tempo** datasource from the dropdown
3. Click the **Search** tab
4. Set **Service Name** → `kong-gateway`
5. Click **Run query**

You should see one trace per login/register request. Click a trace to expand it:

```
kong-gateway   [root span — full request duration]
  └─ career-roadmap-api   [FastAPI span — auth + DB]
       └─ firebase.verify_token   [Firebase Admin SDK]
```

This waterfall confirms the OTel pipeline is working end-to-end from Kong through FastAPI.

### 9c — Structured logs in Loki

1. In Grafana → **Explore**
2. Select the **Loki** datasource
3. Run this LogQL query:

```logql
{container="crai-kong"} | json
```

You should see structured Kong access log lines with fields like `request`, `response.status`, `latencies.proxy`, `service.name`.

For FastAPI logs:

```logql
{container="crai-kong"} or {job="career-roadmap-api"} | json | event != ""
```

---

## Step 10 — Trigger a roadmap generation (full pipeline test)

Once logged in, submit a career goal from the dashboard. This exercises the full async pipeline:

```
Browser → Kong (:8080) → FastAPI → Celery task → LangGraph orchestrator
→ AgentEvents via Redis pub/sub
→ GET /stream/{session_id} SSE → Browser
```

**What to check:**
- The SSE connection in DevTools → Network shows `EventStream` type with a continuous stream of events
- The Celery worker terminal shows task logs
- Tempo shows a new trace with spans across Kong, FastAPI, and the orchestrator

---

## Step 11 — Tear down

Order matters: purge Celery tasks **while Redis is still running**, then stop everything.

```bash
# 1. Ctrl+C the Celery worker (its terminal)

# 2. Purge leftover tasks from the broker NOW — Redis must still be up
make worker-purge

# 3. Ctrl+C FastAPI (its terminal)
# 4. Ctrl+C Next.js (its terminal)

# 5. Stop background processes
make mcp-stop           # kill all 6 MCP server process trees
make gateway-obs-down   # stop Kong + all observability containers
```

Skipping step 2 means any queued tasks survive in the Redis volume and will replay the next time you run `make worker`.

---

## Quick reference

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:3000 | Next.js app |
| Kong proxy | http://localhost:8080 | Single entry point for all API calls |
| Kong Admin | http://localhost:8001 | Route / plugin inspection (`make gateway-admin`) |
| FastAPI docs | http://localhost:8000/docs | Swagger UI (dev only, direct access) |
| Grafana | http://localhost:3300 | Dashboards — Kong + API metrics |
| Prometheus | http://localhost:9090 | Raw metrics + scrape target status |
| Tempo | http://localhost:3200 | Distributed trace storage |
| Loki | http://localhost:3100 | Log aggregation |
| MCP — Job Board | http://localhost:3001 | Job postings (LinkedIn, Indeed, Swiss Jobs) |
| MCP — Course Catalogue | http://localhost:3002 | Courses (100+ curated + Coursera public API; Udemy/YouTube/O'Reilly optional) |
| MCP — Salary Benchmark | http://localhost:3003 | Salary ranges (levels.fyi, curated dataset) |
| MCP — GitHub Trends | http://localhost:3004 | Trending repos + good-first-issues |
| MCP — Social Signals | http://localhost:3005 | HackerNews, Reddit, Dev.to signals |
| MCP — Industry News | http://localhost:3007 | RSS feeds + NewsAPI digest |

**Worker commands:**

| Command | Action |
|---|---|
| `make worker` | Start Celery worker in foreground (Ctrl+C to stop) |
| `make worker-purge` | Discard all pending tasks from the broker queues |
| `make worker-flush` | Flush Redis DB1 (broker) + DB2 (results) entirely — harder reset |

> Run `make worker-purge` **before** `make gateway-obs-down` during teardown, and **after** `make gateway-obs-up` during startup, whenever you are restarting the stack across sessions.

**MCP commands:**

| Command | Action |
|---|---|
| `make mcp-start` | Start all 6 servers in background + wait for health |
| `make mcp-stop` | Stop all 6 servers (full process tree kill) |
| `make mcp-restart` | Stop all → start all + health check |
| `make mcp-status` | Show UP/DOWN status for all 6 servers |
| `make mcp-logs` | Tail all server logs interleaved (Ctrl+C to stop) |
| | |
| `make mcp-stop-<name>` | Stop one server, e.g. `mcp-stop-course-catalogue` |
| `make mcp-restart-<name>` | Restart one server, e.g. `mcp-restart-social-signals` |
| `make mcp-logs-<name>` | Tail one server's log, e.g. `mcp-logs-github-trends` |

Valid `<name>` values: `job-board`, `course-catalogue`, `salary-benchmark`, `github-trends`, `social-signals`, `industry-news`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `curl` returns `Invoke-WebRequest` output or a security prompt | Use `curl.exe` instead of `curl` in PowerShell |
| Browser network requests go to `:8000` instead of `:8080` | `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` is wrong — set it to `http://localhost:8080` and restart `make web-dev` |
| `X-Kong-Proxy-Latency` header missing | Kong container is not running — run `make gateway-up` |
| `make gateway-admin` prints "Kong is not reachable" | Kong is not started — run `make gateway-obs-up` first |
| Prometheus target `kong` is DOWN | Kong `gateway` profile not started — run `make gateway-obs-up` |
| Grafana dashboards are empty | Wait 15–30 s for first scrape, or check Prometheus targets at `:9090/targets` |
| No traces in Tempo | `OTEL_TRACING_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` must be set in `apps/api/.env` — restart FastAPI after changing |
| Kong returns `503` | The upstream (FastAPI or MCP server) is not running — start it first |
| Login returns `CORS` error | `CORS_ORIGINS` in `apps/api/.env` must be a JSON array `["http://localhost:3000"]` — verify and restart FastAPI |
| Worker replays old tasks after `infra-down` / `infra-up` | Redis persists broker state to a Docker volume — run `make worker-purge` after infra-up and before `make worker` |
| Celery worker crashes with `PermissionError` on Windows | The Makefile now uses `--pool=solo` on Windows automatically — pull latest Makefile |
| `ValidationError: reranker_top_n` on startup | Set `RERANKER_TOP_N=20` in `apps/api/.env` (must be an integer, not blank) |
| FastAPI returns `{"detail": "Not Found"}` via Kong | Check the path — liveness probe is `/livez` (with a `z`), not `/live` |
| Grafana not accessible at `:3001` | Grafana runs on `:3300` — `:3001` is reserved for MCP job-board |
| Celery `soft timeout` warning on Windows | Expected — Windows has no `SIGUSR1`. Tasks still run correctly with `--pool=solo` |
| `make mcp-start` hangs or times out | Check `logs/mcp/<name>.log.err` for import errors; run `make install-api` to ensure all packages are installed |
| `make mcp-status` shows all DOWN | Run `make mcp-start` first; if already running, check that `apps/api/.venv/Scripts/uvicorn.exe` exists |
| Agents still use stub data after setting MCP URLs | Restart FastAPI (`Ctrl+C` then `make dev`) — env vars are read at startup |
| MCP server crashes on import | PYTHONPATH may be wrong; verify each server's `logs/mcp/<name>.log.err` shows `Application startup complete` |
| Code changes to an MCP server have no effect | The uvicorn reloader may be stuck with stale `.pyc` files — run `make mcp-restart-<name>` to kill the full process tree and relaunch cleanly |
| `make mcp-stop` doesn't kill the server | The process may have been started outside the scripts (no PID file); `make mcp-stop` falls back to port-based kill with `taskkill /T /F`, which should always work |
| Course catalogue returns 0 courses | This was a known bug (fixed): `BaseCourseClient` lazy-init was missing and the edX Discovery API requires auth. Now fixed — curated dataset + Coursera public API are always active with no API keys needed |
