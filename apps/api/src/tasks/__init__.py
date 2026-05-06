"""apps.api.tasks — Celery worker entry-point for the API process.

The Celery app instance and all task definitions live in ``agents.bus``.
This package sets up the worker environment (logging, Sentry, etc.) and
re-exports the shared ``celery_app`` so that the worker can be started with:

    celery -A src.tasks.worker worker --loglevel=info -Q agents.default,agents.priority
"""
