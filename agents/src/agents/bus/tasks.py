"""Celery task definitions — the actual functions executed by workers.

These are deliberately thin: they handle only Celery ceremony (task
lifecycle, retry policy, logging setup) and immediately delegate to
``MasterOrchestrator`` or ``BaseAgent.run()``. No business logic lives here.

Workers are started with::

    celery -A agents.bus.celery_app worker --loglevel=info -Q agents.default,agents.priority
"""
import asyncio
from typing import TYPE_CHECKING

import structlog
from celery import Task

from agents.bus.celery_app import celery_app
from agents.config import agent_settings
from agents.contracts.results import AgentResultStatus, OrchestratorResult
from agents.contracts.tasks import AgentTaskInput, OrchestratorTaskInput
from agents.core.exceptions import AgentError
from agents.core.logging import configure_agent_logging

if TYPE_CHECKING:
    from agents.persistence.interfaces import IRoadmapStore

logger = structlog.get_logger(__name__)


async def _build_roadmap_store() -> "IRoadmapStore":
    """Return the configured roadmap store — Firestore or no-op.

    Late-imported so the Firestore client (google-cloud-firestore) is only
    pulled in when persistence is enabled, keeping cold-start cost low.
    """
    if not agent_settings.firestore_persistence_enabled:
        from agents.persistence.noop_store import NoOpRoadmapStore  # noqa: PLC0415
        return NoOpRoadmapStore()
    try:
        from agents.persistence.firestore_store import FirestoreRoadmapStore  # noqa: PLC0415
        return await FirestoreRoadmapStore.from_settings(agent_settings)
    except Exception as exc:
        logger.warning("roadmap.store.init_failed", error=str(exc))
        from agents.persistence.noop_store import NoOpRoadmapStore  # noqa: PLC0415
        return NoOpRoadmapStore()


async def _run_orchestration_pipeline(
    task_input: OrchestratorTaskInput,
) -> OrchestratorResult:
    """Run orchestration and persist the result in a single event loop."""
    from agents.orchestrator.orchestrator import MasterOrchestrator  # noqa: PLC0415

    store = await _build_roadmap_store()
    orchestrator = MasterOrchestrator()
    result = await orchestrator.run(task_input)

    if result.status == AgentResultStatus.COMPLETED and result.roadmap:
        try:
            roadmap_id = await store.save(result)
            logger.info(
                "orchestration.roadmap_persisted",
                roadmap_id=roadmap_id,
                user_id=result.user_id,
                session_id=result.session_id,
            )
        except Exception as exc:
            # Persistence failure must not fail the task — the roadmap was
            # already delivered to the client via SSE.
            logger.error(
                "orchestration.persist_failed",
                error=str(exc),
                user_id=result.user_id,
                exc_info=True,
            )

    return result


class _BaseAgentTask(Task):
    """Celery Task base with agent-side logging and dead-letter routing."""

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        logger.error("celery.task.failed", task_id=task_id, error=str(exc))
        # Route to dead-letter queue so ops can inspect and replay failed tasks.
        try:
            celery_app.send_task(
                "agents.bus.tasks.receive_dead_letter",
                kwargs={
                    "task_id": task_id,
                    "task_name": self.name,
                    "error": str(exc),
                    "original_kwargs": kwargs,
                },
                queue="agents.dead_letter",
            )
        except Exception as dl_exc:
            logger.warning(
                "celery.dead_letter.route_failed",
                task_id=task_id,
                error=str(dl_exc),
            )

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        logger.warning("celery.task.retrying", task_id=task_id, error=str(exc))


@celery_app.task(
    bind=True,
    base=_BaseAgentTask,
    name="agents.bus.tasks.run_orchestration",
    max_retries=4,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def run_orchestration(self: Task, payload: dict) -> dict:
    """Execute a full orchestration pipeline for one user generation request.

    Called once per ``POST /api/v1/orchestrator/generate`` request.
    Runs the async ``MasterOrchestrator.run()`` inside a fresh event loop.
    """
    configure_agent_logging()
    task_input = OrchestratorTaskInput.model_validate(payload)

    log = logger.bind(
        request_id=task_input.request_id,
        user_id=task_input.user_id,
        session_id=task_input.session_id,
    )
    log.info("orchestration.task.started")

    try:
        result = asyncio.run(_run_orchestration_pipeline(task_input))
        log.info("orchestration.task.completed", status=result.status.value)
        return result.model_dump(mode="json")

    except AgentError as exc:
        log.error("orchestration.task.agent_error", error=str(exc))
        raise self.retry(exc=exc) from exc
    except Exception as exc:
        log.error("orchestration.task.unexpected_error", error=str(exc), exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=_BaseAgentTask,
    name="agents.bus.tasks.run_agent",
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def run_agent(self: Task, payload: dict) -> dict:
    """Execute a single specialist agent.

    Used when the orchestrator chooses to fan out sub-tasks via Celery
    rather than running them in-process with asyncio.gather (e.g., for
    long-running or resource-intensive agents).
    """
    configure_agent_logging()
    task_input = AgentTaskInput.model_validate(payload)

    log = logger.bind(
        task_id=task_input.task_id,
        agent_type=task_input.agent_type.value,
        user_id=task_input.user_id,
        correlation_id=task_input.correlation_id,
    )
    log.info("agent.task.started")

    try:
        from agents.core.agent_registry import registry  # noqa: PLC0415
        from agents.core.context import AgentContext  # noqa: PLC0415
        from agents.bus.channel import channel_for_session  # noqa: PLC0415

        agent = registry.get(task_input.agent_type)
        context = AgentContext(
            task_id=task_input.task_id,
            session_id=task_input.session_id,
            user_id=task_input.user_id,
            correlation_id=task_input.correlation_id,
            stream_channel=channel_for_session(task_input.user_id, task_input.session_id),
            user_profile=task_input.user_profile,
            user_message=task_input.payload.get("user_message", ""),
        )
        result = asyncio.run(agent.run(context))
        log.info("agent.task.completed", status=result.status.value)
        return result.model_dump(mode="json")

    except Exception as exc:
        log.error("agent.task.failed", error=str(exc), exc_info=True)
        raise


@celery_app.task(
    name="agents.bus.tasks.receive_dead_letter",
    queue="agents.dead_letter",
    ignore_result=True,
)
def receive_dead_letter(
    task_id: str,
    task_name: str,
    error: str,
    original_kwargs: dict,
) -> None:
    """Accept a failed task routed to the dead-letter queue.

    Logs full context so ops can review and decide on manual replay.
    In future iterations this can push to PagerDuty, Slack, or a DB table.
    """
    configure_agent_logging()
    logger.error(
        "dead_letter.received",
        original_task_id=task_id,
        task_name=task_name,
        error=error,
        payload_keys=list(original_kwargs.keys()),
    )


@celery_app.task(
    name="agents.bus.tasks.cleanup_dead_letter",
    ignore_result=True,
)
def cleanup_dead_letter() -> None:
    """Nightly beat task — logs dead-letter queue depth for ops visibility.

    A real cleanup (TTL-based purge or replay) can be wired here once a
    persistent dead-letter store (e.g., Postgres table or Redis sorted set)
    is in place.  For now this task surfaces the queue as a health signal.
    """
    configure_agent_logging()
    try:
        from kombu import Connection  # noqa: PLC0415

        with Connection(celery_app.conf.broker_url) as conn:
            with conn.channel() as channel:
                _, count, _ = channel.queue_declare(
                    queue="agents.dead_letter", passive=True
                )
                logger.info("dead_letter.queue_depth", count=count)
    except Exception as exc:
        logger.warning("dead_letter.cleanup_check_failed", error=str(exc))
