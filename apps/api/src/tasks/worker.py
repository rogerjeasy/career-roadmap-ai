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

    _register_agents()

    import structlog  # noqa: PLC0415
    logger = structlog.get_logger("celery.worker")
    logger.info("celery.worker.started", environment=settings.environment)


def _register_agents() -> None:
    """Register all specialist agents in the process-local registry.

    Called once per worker process from on_worker_init so every agent is
    available before the first orchestration task runs.  Late imports keep
    cold-start cost low for processes that never run orchestration tasks.
    """
    import redis as _redis  # noqa: PLC0415
    import structlog  # noqa: PLC0415
    from agents.bus.publisher import EventPublisher  # noqa: PLC0415
    from agents.coach.coach_agent import CoachAgent  # noqa: PLC0415
    from agents.config import agent_settings  # noqa: PLC0415
    from agents.core.agent_registry import registry  # noqa: PLC0415
    from agents.cv_analysis.cv_agent import CVAgent  # noqa: PLC0415
    from agents.gap_analysis.gap_agent import GapAgent  # noqa: PLC0415
    from agents.intake.intake_agent import IntakeAgent  # noqa: PLC0415
    from agents.learning_resources.learning_agent import LearningAgent  # noqa: PLC0415
    from agents.market_intelligence.market_agent import MarketAgent  # noqa: PLC0415
    from agents.networking.networking_agent import NetworkingAgent  # noqa: PLC0415
    from agents.opportunity.opportunity_agent import OpportunityAgent  # noqa: PLC0415
    from agents.progress.progress_agent import ProgressAgent  # noqa: PLC0415
    from agents.roadmap_generation.roadmap_agent import RoadmapAgent  # noqa: PLC0415

    _r = _redis.from_url(str(agent_settings.redis_url), decode_responses=True)
    _pub = EventPublisher(_r)

    for agent in [
        IntakeAgent(event_publisher=_pub),
        CVAgent(event_publisher=_pub),
        MarketAgent(event_publisher=_pub),
        GapAgent(event_publisher=_pub),
        RoadmapAgent(event_publisher=_pub),
        LearningAgent(event_publisher=_pub),
        NetworkingAgent(event_publisher=_pub),
        OpportunityAgent(event_publisher=_pub),
        ProgressAgent(event_publisher=_pub),
        CoachAgent(event_publisher=_pub),
    ]:
        registry.register(agent)

    structlog.get_logger("celery.worker").info(
        "celery.worker.agents_registered",
        count=len(registry.available()),
        agents=[a.value for a in registry.available()],
    )


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
