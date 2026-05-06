"""Celery worker bootstrap for the API process.

Imports the shared Celery app from the agents package and applies
API-side configuration (Sentry for the worker, structlog, signal hooks).

Start the worker with:
    celery -A src.tasks.worker worker --loglevel=info \\
           -Q agents.default,agents.priority --concurrency=4
"""
from celery.signals import worker_init, worker_shutdown, task_failure

from agents.bus.celery_app import celery_app  # noqa: F401 — Celery autodiscovery
from agents.core.logging import configure_agent_logging
from src.config import settings


@worker_init.connect
def on_worker_init(**_kwargs) -> None:
    """Initialise per-process singletons when a Celery worker starts."""
    configure_agent_logging()

    # Mirror API-side Sentry setup so worker errors are also captured
    if settings.sentry_dsn:
        import sentry_sdk  # noqa: PLC0415
        from sentry_sdk.integrations.celery import CeleryIntegration  # noqa: PLC0415

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[CeleryIntegration()],
            traces_sample_rate=settings.sentry_traces_sample_rate,
            environment=settings.environment,
        )

    import structlog  # noqa: PLC0415
    logger = structlog.get_logger("celery.worker")
    logger.info("celery.worker.started", environment=settings.environment)


@worker_shutdown.connect
def on_worker_shutdown(**_kwargs) -> None:
    import structlog  # noqa: PLC0415
    structlog.get_logger("celery.worker").info("celery.worker.stopped")


@task_failure.connect
def on_task_failure(task_id, exception, **_kwargs) -> None:
    import structlog  # noqa: PLC0415
    structlog.get_logger("celery.task").error(
        "celery.task.failure",
        task_id=task_id,
        error=str(exception),
    )
