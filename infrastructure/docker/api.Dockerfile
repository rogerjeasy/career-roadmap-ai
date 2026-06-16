# Career Roadmap AI — combined API + Celery worker image (free-tier / portfolio).
#
# Runs BOTH uvicorn (FastAPI) and a Celery worker in one container so the whole
# backend fits in a single free Render web service. For real scale, split these
# back into separate services (api.Dockerfile + worker.Dockerfile).
#
# Build context MUST be the repo root:
#     docker build -f infrastructure/docker/api.Dockerfile -t career-api .
#
# The agents package is NOT pip-installed separately (its openai<2 pin conflicts
# with the API's openai>=2.33). Instead its source is placed on PYTHONPATH, and
# the few deps it needs beyond the API's set are installed explicitly below.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for asyncpg / grpc / cryptography wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Install the API package + all its dependencies (the superset).
COPY apps/api/pyproject.toml apps/api/README.md ./apps/api/
COPY apps/api/src ./apps/api/src
RUN pip install ./apps/api

# 2) Extra deps the worker needs that aren't in the API manifest.
#    (agents pulls these; installed without touching the resolved openai 2.x.)
RUN pip install \
    "google-cloud-firestore>=2.11.0,<3.0.0" \
    "google-auth>=2.0.0,<3.0.0" \
    "opentelemetry-instrumentation-celery>=0.62b1,<0.63"

# 3) Agents source on PYTHONPATH — imported as `agents.*`, not pip-installed.
COPY agents/src/agents ./agents/src/agents
ENV PYTHONPATH=/app/agents/src

# 4) Alembic migrations (run on boot by start.sh).
COPY apps/api/alembic.ini ./apps/api/alembic.ini
COPY apps/api/alembic ./apps/api/alembic

COPY infrastructure/docker/start.sh ./start.sh
RUN chmod +x ./start.sh

# Render injects $PORT; default to 8000 for local runs.
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/apps/api
CMD ["/app/start.sh"]
