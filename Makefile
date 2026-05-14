# Career Roadmap AI — monorepo task runner
#
# Usage:
#   make install        → full first-time setup (agents + api + web)
#   make dev            → start Docker infra + API dev server
#   make dev-full       → infra + gateway + observability + API (everything)
#   make gateway-up     → start Kong API Gateway only
#   make gateway-obs-up → start Kong + full observability stack
#   make worker         → start Celery worker
#   make test           → run all test suites
#   make lint           → lint all packages
#   make help           → list all targets
#
# Prerequisites: Python 3.12+, Poetry 2+, Docker Desktop, Node.js 20+

.PHONY: install install-agents install-api install-web install-hooks \
        dev dev-full \
        infra-up infra-down \
        gateway-up gateway-down gateway-reload gateway-logs gateway-admin \
        obs-up obs-down \
        gateway-obs-up gateway-obs-down \
        deck-diff deck-sync \
        worker worker-purge worker-flush \
        mcp-start mcp-stop mcp-status mcp-all \
        mcp-job-board mcp-course-catalogue mcp-social-signals mcp-calendar \
        mcp-salary-benchmark mcp-github-trends mcp-industry-news \
        mcp-linkedin-profile mcp-document-store \
        mcp-stop-job-board mcp-stop-course-catalogue mcp-stop-salary-benchmark \
        mcp-stop-github-trends mcp-stop-social-signals mcp-stop-industry-news \
        mcp-stop-linkedin-profile mcp-stop-document-store \
        mcp-restart \
        mcp-restart-job-board mcp-restart-course-catalogue mcp-restart-salary-benchmark \
        mcp-restart-github-trends mcp-restart-social-signals mcp-restart-industry-news \
        mcp-restart-linkedin-profile mcp-restart-document-store \
        mcp-logs \
        mcp-logs-job-board mcp-logs-course-catalogue mcp-logs-salary-benchmark \
        mcp-logs-github-trends mcp-logs-social-signals mcp-logs-industry-news \
        mcp-logs-linkedin-profile mcp-logs-document-store \
        web-dev web-build web-typecheck web-lint \
        test test-api test-agents test-web test-e2e \
        lint lint-api lint-agents format \
        db-migrate db-rollback \
        clean help

# ── Paths ─────────────────────────────────────────────────────────────────────

AGENTS_DIR   := agents
API_DIR      := apps/api
WEB_DIR      := apps/web
API_VENV     := $(API_DIR)/.venv
API_PIP      := $(API_VENV)/Scripts/pip   # Windows — change to bin/pip on Linux/macOS
API_PYTHON   := $(API_VENV)/Scripts/python
# MCP servers share the api venv (all packages are already installed there)
# On Linux/macOS change Scripts → bin
API_UVICORN  := $(API_VENV)/Scripts/uvicorn
MCP_SERVERS_DIR := mcp-servers
KONG_DIR     := infrastructure/kong

# Single docker compose invocation rooted at the repo root.
# Volume paths in docker-compose.dev.yml are always resolved relative to the
# compose file's own directory, so moving the CWD here is safe.
COMPOSE := docker compose -f $(API_DIR)/docker-compose.dev.yml

# ── OS-specific tooling ───────────────────────────────────────────────────────
# Windows: Make runs targets through Git Bash; npm is a .cmd file and must be
# invoked with the explicit extension, otherwise bash reports "No such file".
# Celery's prefork pool uses POSIX semaphores unavailable on Windows; use solo.
ifeq ($(OS),Windows_NT)
  NPM                := npm.cmd
  CELERY_POOL        := solo
  CELERY_CONCURRENCY := 1
else
  NPM                := npm
  CELERY_POOL        := prefork
  CELERY_CONCURRENCY := 4
endif

# ── Install ───────────────────────────────────────────────────────────────────

install: install-api install-agents install-web  ## Full first-time setup
	@echo ""
	@echo "Setup complete."
	@echo "  Backend:  make dev"
	@echo "  Frontend: make web-dev"
	@echo "  Both:     make dev-full"

install-api:  ## Install the API virtualenv
	cd $(API_DIR) && poetry install

install-agents: install-api  ## Install the agents package into the API venv (editable)
	$(API_PIP) install --upgrade -e ./$(AGENTS_DIR)
	@echo "career-agents installed as editable package in apps/api venv."

install-hooks:  ## Install git pre-commit secret scanner hook
	@chmod +x .git/hooks/pre-commit 2>/dev/null || true
	@echo "pre-commit hook installed. Test it with: make check-secrets"

check-secrets:  ## Run the secret scanner against all staged files (dry-run friendly)
	@$(API_PYTHON) scripts/check_secrets.py || true

install-web:  ## Install frontend dependencies
	cd $(WEB_DIR) && $(NPM) install

# ── Core infrastructure ───────────────────────────────────────────────────────

infra-up:  ## Start Postgres + Redis + Kong + Tempo (always-on services)
	$(COMPOSE) up -d
	@echo "Core infra running: PostgreSQL → :5432  Redis → :6379  Kong → :8080  Tempo OTLP → :4317"

infra-down:  ## Stop all Docker Compose services (all profiles)
	$(COMPOSE) --profile observability down

# ── Development ───────────────────────────────────────────────────────────────

dev: infra-up  ## Start core infra (Postgres + Redis + Kong) + API dev server
	cd $(API_DIR) && poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 \
		--reload-delay 1.5 \
		--timeout-graceful-shutdown 2

dev-full: obs-up  ## Start infra + Kong + observability, then API dev server
	@echo ""
	@echo "Infrastructure ready:"
	@echo "  Kong proxy  → http://localhost:8080"
	@echo "  FastAPI     → http://localhost:8000 (direct)"
	@echo "  Grafana     → http://localhost:3300"
	@echo "  Prometheus  → http://localhost:9090"
	@echo ""
	cd $(API_DIR) && poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 \
		--reload-delay 1.5 \
		--timeout-graceful-shutdown 2

# ── API Gateway (Kong) ────────────────────────────────────────────────────────
# Kong is always-on — started automatically by infra-up / make dev.
# These targets manage the running container without touching the full stack.

gateway-up: infra-up  ## Alias for infra-up (Kong is always included)

gateway-down:  ## Stop the Kong container only (leaves Postgres + Redis running)
	$(COMPOSE) stop kong
	$(COMPOSE) rm -f kong

gateway-reload:  ## Apply kong.dev.yml changes without a full restart
	$(COMPOSE) restart kong
	@echo "Kong reloaded — new config active."

gateway-logs:  ## Tail Kong proxy access + error logs
	$(COMPOSE) logs -f kong

gateway-admin:  ## Smoke-test the Kong Admin API (lists all routes)
	@echo "=== Kong Admin API — routes ===" && \
	curl -sf http://localhost:8001/routes | $(API_PYTHON) -m json.tool 2>/dev/null || \
	curl -s http://localhost:8001/routes || \
	echo "Kong is not reachable at localhost:8001 — run 'make dev' first."

# ── Observability stack ───────────────────────────────────────────────────────

obs-up: infra-up  ## Start observability stack (Tempo + Prometheus + Loki + Grafana)
	$(COMPOSE) --profile observability up -d
	@echo ""
	@echo "Observability stack started:"
	@echo "  Grafana    → http://localhost:3300"
	@echo "  Prometheus → http://localhost:9090"
	@echo "  Tempo      → http://localhost:3200"
	@echo "  Loki       → http://localhost:3100"
	@echo ""
	@echo "Enable tracing in .env:"
	@echo "  OTEL_TRACING_ENABLED=true"
	@echo "  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317"

obs-down:  ## Stop observability stack only
	$(COMPOSE) --profile observability stop

gateway-obs-up: obs-up  ## Start Kong (always-on) + full observability stack together
	@echo ""
	@echo "Kong + Observability running:"
	@echo "  Kong proxy  → http://localhost:8080"
	@echo "  Grafana     → http://localhost:3300  (Kong dashboard: uid=kong-gateway)"
	@echo "  Prometheus  → http://localhost:9090"
	@echo "  Tempo       → http://localhost:3200"

gateway-obs-down:  ## Stop observability stack (Kong stays running with infra)
	$(COMPOSE) --profile observability down

# ── Production Kong config (deck) ─────────────────────────────────────────────
# Requires: deck CLI (https://docs.konghq.com/deck/latest/installation/)
#           .env.production populated from infrastructure/kong/deck.env.example
#           Kong Admin API accessible (port-forwarded or inside VPC)

DECK_STATE     := $(KONG_DIR)/kong.yml
DECK_ENV_FILE  := $(KONG_DIR)/.env.production
KONG_ADDR      ?= https://$(shell terraform -chdir=infrastructure/terraform/environments/production output -raw kong_proxy_fqdn 2>/dev/null || echo "localhost:8001")

deck-diff:  ## Diff local kong.yml against the live Kong cluster (dry run)
	deck diff \
		--state $(DECK_STATE) \
		--env-file $(DECK_ENV_FILE) \
		--kong-addr $(KONG_ADDR)

deck-sync:  ## Push infrastructure/kong/kong.yml to the live Kong cluster
	@echo "Syncing Kong config to $(KONG_ADDR)..."
	deck sync \
		--state $(DECK_STATE) \
		--env-file $(DECK_ENV_FILE) \
		--kong-addr $(KONG_ADDR)
	@echo "Kong config synced."

# ── Frontend ──────────────────────────────────────────────────────────────────

ifeq ($(OS),Windows_NT)
web-dev:  ## Start Next.js development server (proxies to Kong at :8080)
	powershell.exe -NoProfile -Command "Set-Location $(WEB_DIR); npm run dev"
else
web-dev:  ## Start Next.js development server (proxies to Kong at :8080)
	cd $(WEB_DIR) && $(NPM) run dev
endif

web-build:  ## Production build of the Next.js app
	cd $(WEB_DIR) && $(NPM) run build

web-typecheck:  ## Run TypeScript type checking
	cd $(WEB_DIR) && $(NPM) run typecheck

web-lint:  ## Lint frontend code
	cd $(WEB_DIR) && $(NPM) run lint

# ── MCP Servers ───────────────────────────────────────────────────────────────
# All 9 MCP servers share apps/api/.venv (no separate 'poetry install' needed).
# Set MCP_*_URL vars in apps/api/.env to route agents to the live servers.
#
# Recommended workflow on Windows:
#   make mcp-start    → start all 9 servers in the background (logs in logs/mcp/)
#   make mcp-status   → health check all 9 servers
#   make mcp-stop     → stop all 9 servers
#
# Individual one-shot servers (foreground, for debugging):
#   make mcp-salary-benchmark   make mcp-github-trends   make mcp-industry-news

MCP_SCRIPT_START  := powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-mcp-servers.ps1
MCP_SCRIPT_STOP   := powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/stop-mcp-servers.ps1
MCP_SCRIPT_STATUS := powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/status-mcp-servers.ps1

mcp-start:  ## Start all 6 MCP servers in background (logs → logs/mcp/<name>.log)
	$(MCP_SCRIPT_START) -WaitForHealth

mcp-stop:  ## Stop all running MCP servers
	$(MCP_SCRIPT_STOP)

mcp-status:  ## Show health status for all MCP servers
	$(MCP_SCRIPT_STATUS)

# ── Individual MCP servers (foreground, blocking — useful for debugging a single server) ──
# Each sets PYTHONPATH for the shared api venv and runs uvicorn in this terminal.

mcp-job-board:  ## Start Job Board MCP server (port 3001) in foreground
	$(MCP_SCRIPT_START) -Servers job-board

mcp-course-catalogue:  ## Start Course Catalogue MCP server (port 3002) in foreground
	$(MCP_SCRIPT_START) -Servers course-catalogue

mcp-salary-benchmark:  ## Start Salary Benchmark MCP server (port 3003) in foreground
	$(MCP_SCRIPT_START) -Servers salary-benchmark

mcp-github-trends:  ## Start GitHub Trends MCP server (port 3004) in foreground
	$(MCP_SCRIPT_START) -Servers github-trends

mcp-social-signals:  ## Start Social Signals MCP server (port 3005) in foreground
	$(MCP_SCRIPT_START) -Servers social-signals

mcp-calendar:  ## Start Calendar MCP server (port 3006) in foreground
	$(MCP_SCRIPT_START) -Servers calendar

mcp-industry-news:  ## Start Industry News MCP server (port 3007) in foreground
	$(MCP_SCRIPT_START) -Servers industry-news

mcp-linkedin-profile:  ## Start LinkedIn Profile MCP server (port 3008) in foreground
	$(MCP_SCRIPT_START) -Servers linkedin-profile

mcp-document-store:  ## Start Document Store MCP server (port 3009) in foreground
	$(MCP_SCRIPT_START) -Servers document-store

mcp-all:  ## Alias for mcp-start (starts all servers in background)
	$(MCP_SCRIPT_START) -WaitForHealth

# ── Individual stop targets ────────────────────────────────────────────────────
# Kills the full uvicorn process tree (reloader parent + worker child).
# Safe to run even if the server is not currently running.

mcp-stop-job-board:  ## Stop Job Board MCP server (port 3001)
	$(MCP_SCRIPT_STOP) -Servers job-board

mcp-stop-course-catalogue:  ## Stop Course Catalogue MCP server (port 3002)
	$(MCP_SCRIPT_STOP) -Servers course-catalogue

mcp-stop-salary-benchmark:  ## Stop Salary Benchmark MCP server (port 3003)
	$(MCP_SCRIPT_STOP) -Servers salary-benchmark

mcp-stop-github-trends:  ## Stop GitHub Trends MCP server (port 3004)
	$(MCP_SCRIPT_STOP) -Servers github-trends

mcp-stop-social-signals:  ## Stop Social Signals MCP server (port 3005)
	$(MCP_SCRIPT_STOP) -Servers social-signals

mcp-stop-industry-news:  ## Stop Industry News MCP server (port 3007)
	$(MCP_SCRIPT_STOP) -Servers industry-news

mcp-stop-linkedin-profile:  ## Stop LinkedIn Profile MCP server (port 3008)
	$(MCP_SCRIPT_STOP) -Servers linkedin-profile

mcp-stop-document-store:  ## Stop Document Store MCP server (port 3009)
	$(MCP_SCRIPT_STOP) -Servers document-store

# ── Restart targets ────────────────────────────────────────────────────────────
# Stops (full tree kill) then re-launches with health check.
# Use these after code changes to pick up the new code without stale .pyc files.

mcp-restart:  ## Restart all MCP servers (stop full trees, then start + health check)
	$(MCP_SCRIPT_STOP)
	$(MCP_SCRIPT_START) -WaitForHealth

mcp-restart-job-board:  ## Restart Job Board MCP server
	$(MCP_SCRIPT_STOP) -Servers job-board
	$(MCP_SCRIPT_START) -Servers job-board -WaitForHealth

mcp-restart-course-catalogue:  ## Restart Course Catalogue MCP server
	$(MCP_SCRIPT_STOP) -Servers course-catalogue
	$(MCP_SCRIPT_START) -Servers course-catalogue -WaitForHealth

mcp-restart-salary-benchmark:  ## Restart Salary Benchmark MCP server
	$(MCP_SCRIPT_STOP) -Servers salary-benchmark
	$(MCP_SCRIPT_START) -Servers salary-benchmark -WaitForHealth

mcp-restart-github-trends:  ## Restart GitHub Trends MCP server
	$(MCP_SCRIPT_STOP) -Servers github-trends
	$(MCP_SCRIPT_START) -Servers github-trends -WaitForHealth

mcp-restart-social-signals:  ## Restart Social Signals MCP server
	$(MCP_SCRIPT_STOP) -Servers social-signals
	$(MCP_SCRIPT_START) -Servers social-signals -WaitForHealth

mcp-restart-industry-news:  ## Restart Industry News MCP server
	$(MCP_SCRIPT_STOP) -Servers industry-news
	$(MCP_SCRIPT_START) -Servers industry-news -WaitForHealth

mcp-restart-linkedin-profile:  ## Restart LinkedIn Profile MCP server
	$(MCP_SCRIPT_STOP) -Servers linkedin-profile
	$(MCP_SCRIPT_START) -Servers linkedin-profile -WaitForHealth

mcp-restart-document-store:  ## Restart Document Store MCP server
	$(MCP_SCRIPT_STOP) -Servers document-store
	$(MCP_SCRIPT_START) -Servers document-store -WaitForHealth

# ── Log tailing ────────────────────────────────────────────────────────────────
# Streams live log output. Press Ctrl+C to stop tailing.

mcp-logs:  ## Tail all MCP server logs interleaved (Ctrl+C to stop)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/*.log -Tail 20 -Wait"

mcp-logs-job-board:  ## Tail Job Board log (logs/mcp/job-board.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/job-board.log -Tail 50 -Wait"

mcp-logs-course-catalogue:  ## Tail Course Catalogue log (logs/mcp/course-catalogue.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/course-catalogue.log -Tail 50 -Wait"

mcp-logs-salary-benchmark:  ## Tail Salary Benchmark log (logs/mcp/salary-benchmark.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/salary-benchmark.log -Tail 50 -Wait"

mcp-logs-github-trends:  ## Tail GitHub Trends log (logs/mcp/github-trends.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/github-trends.log -Tail 50 -Wait"

mcp-logs-social-signals:  ## Tail Social Signals log (logs/mcp/social-signals.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/social-signals.log -Tail 50 -Wait"

mcp-logs-industry-news:  ## Tail Industry News log (logs/mcp/industry-news.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/industry-news.log -Tail 50 -Wait"

mcp-logs-linkedin-profile:  ## Tail LinkedIn Profile log (logs/mcp/linkedin-profile.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/linkedin-profile.log -Tail 50 -Wait"

mcp-logs-document-store:  ## Tail Document Store log (logs/mcp/document-store.log)
	powershell.exe -NoProfile -Command "Get-Content logs/mcp/document-store.log -Tail 50 -Wait"

# ── Worker ────────────────────────────────────────────────────────────────────

worker:  ## Start Celery worker (requires infra-up)
	cd $(API_DIR) && poetry run celery -A src.tasks.worker worker \
		--loglevel=info \
		-Q agents.default,agents.priority,agents.ingestion \
		--pool=$(CELERY_POOL) \
		--concurrency=$(CELERY_CONCURRENCY)

worker-purge:  ## Discard all pending tasks from the Celery queues (run after infra restart)
	cd $(API_DIR) && poetry run celery -A src.tasks.worker purge -f
	@echo "All pending Celery tasks purged."

worker-flush:  ## Flush Celery broker (Redis DB1) + result backend (DB2) — harder reset
	cd $(API_DIR) && poetry run python -c "\
import redis, os; \
url = os.getenv('REDIS_URL', 'redis://localhost:6379/0').rsplit('/', 1)[0]; \
[redis.from_url(url + '/' + str(db)).flushdb() for db in (1, 2)]; \
print('Celery broker (DB1) and result backend (DB2) flushed.')"

# ── Database ──────────────────────────────────────────────────────────────────

db-migrate:  ## Run pending Alembic migrations
	cd $(API_DIR) && poetry run alembic upgrade head

db-rollback:  ## Roll back the last Alembic migration
	cd $(API_DIR) && poetry run alembic downgrade -1

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-api test-agents test-web  ## Run all test suites

test-api:  ## Run API tests
	cd $(API_DIR) && poetry run pytest tests/ -v --tb=short

test-agents:  ## Run agents tests
	cd $(AGENTS_DIR) && $(API_PYTHON) -m pytest src/agents/orchestrator/tests/ -v --tb=short

test-web:  ## Run frontend unit/component tests
	cd $(WEB_DIR) && $(NPM) test

test-e2e:  ## Run Playwright end-to-end tests (requires running dev stack)
	cd $(WEB_DIR) && $(NPM) run test:e2e

# ── Code quality ──────────────────────────────────────────────────────────────

lint: lint-api lint-agents web-lint  ## Lint all packages

lint-api:
	cd $(API_DIR) && poetry run ruff check src/ && poetry run ruff format --check src/

lint-agents:
	cd $(AGENTS_DIR) && $(API_PYTHON) -m ruff check src/ && $(API_PYTHON) -m ruff format --check src/

format:  ## Auto-format all packages
	cd $(API_DIR) && poetry run ruff format src/
	cd $(AGENTS_DIR) && $(API_PYTHON) -m ruff format src/

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:  ## Remove all build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

# ── Help ──────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
