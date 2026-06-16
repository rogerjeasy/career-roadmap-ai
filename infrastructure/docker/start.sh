#!/usr/bin/env bash
# Boots the combined API + Celery worker for free-tier (portfolio) hosting.
#
#   1. Run DB migrations (best-effort; won't crash the box if Postgres is down)
#   2. Start a Celery worker in the background (low concurrency to fit 512 MB)
#   3. Start uvicorn in the foreground (PID 1 → receives signals from Render)
#
# If the worker dies, the container keeps serving HTTP. For a demo that's the
# right trade-off; for production, supervise both with a real process manager.
set -euo pipefail

echo "[start] running alembic migrations..."
alembic upgrade head || echo "[start] WARN: migrations failed/skipped, continuing"

# Concurrency 1 + no prefork pool overhead keeps the worker inside free RAM.
echo "[start] launching celery worker..."
celery -A agents.bus.celery_app worker \
  --loglevel=info \
  --concurrency=1 \
  --pool=solo \
  --without-gossip --without-mingle --without-heartbeat &

echo "[start] launching uvicorn on :${PORT:-8000}..."
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
