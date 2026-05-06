# Career Roadmap AI — monorepo task runner
#
# Usage:
#   make install      → full first-time setup (agents + api)
#   make dev          → start Docker infra + API dev server
#   make worker       → start Celery worker
#   make test         → run all test suites
#   make lint         → lint all packages
#
# Prerequisites: Python 3.12+, Poetry 2+, Docker Desktop

.PHONY: install install-agents install-api dev worker test test-api test-agents lint clean help obs-up obs-down

# ── Paths ─────────────────────────────────────────────────────────────────────
AGENTS_DIR   := agents
API_DIR      := apps/api
API_VENV     := $(API_DIR)/.venv
API_PIP      := $(API_VENV)/Scripts/pip   # Windows — change to bin/pip on Linux/macOS
API_PYTHON   := $(API_VENV)/Scripts/python

# ── Install ───────────────────────────────────────────────────────────────────

install: install-api install-agents  ## Full first-time setup
	@echo ""
	@echo "Setup complete. Run 'make dev' to start the development server."

install-api:  ## Install the API virtualenv
	cd $(API_DIR) && poetry install

install-agents: install-api  ## Install the agents package into the API venv (editable)
	$(API_PIP) install -e ./$(AGENTS_DIR)
	@echo "career-agents installed as editable package in apps/api venv."

# ── Development ───────────────────────────────────────────────────────────────

dev: infra-up  ## Start Docker infra and the API dev server
	cd $(API_DIR) && poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

infra-up:  ## Start Postgres + Redis via Docker Compose
	cd $(API_DIR) && docker compose -f docker-compose.dev.yml up -d

infra-down:  ## Stop Docker Compose services
	cd $(API_DIR) && docker compose -f docker-compose.dev.yml down

obs-up:  ## Start full observability stack (Tempo + Prometheus + Loki + Grafana)
	cd $(API_DIR) && docker compose -f docker-compose.dev.yml --profile observability up -d
	@echo ""
	@echo "Observability stack started:"
	@echo "  Grafana   → http://localhost:3001"
	@echo "  Prometheus→ http://localhost:9090"
	@echo "  Tempo     → http://localhost:3200"
	@echo "  Loki      → http://localhost:3100"
	@echo ""
	@echo "Enable tracing in .env:"
	@echo "  OTEL_TRACING_ENABLED=true"
	@echo "  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317"

obs-down:  ## Stop observability stack only
	cd $(API_DIR) && docker compose -f docker-compose.dev.yml --profile observability down

worker:  ## Start Celery worker (requires infra-up)
	cd $(API_DIR) && poetry run celery -A src.tasks.worker worker \
		--loglevel=info \
		-Q agents.default,agents.priority \
		--concurrency=4

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-api test-agents  ## Run all tests

test-api:  ## Run API tests
	cd $(API_DIR) && poetry run pytest tests/ -v --tb=short

test-agents:  ## Run agents tests
	cd $(AGENTS_DIR) && $(API_PYTHON) -m pytest src/agents/orchestrator/tests/ -v --tb=short

# ── Code quality ──────────────────────────────────────────────────────────────

lint: lint-api lint-agents  ## Lint all packages

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

# ── Help ──────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
