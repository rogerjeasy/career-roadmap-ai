"""Celery task definitions — the actual functions executed by workers.

These are deliberately thin: they handle only Celery ceremony (task
lifecycle, retry policy, logging setup) and immediately delegate to
``MasterOrchestrator`` or ``BaseAgent.run()``. No business logic lives here.

Workers are started with::

    celery -A agents.bus.celery_app worker --loglevel=info -Q agents.default,agents.priority
"""
import asyncio

import structlog
from celery import Task

from agents.bus.celery_app import celery_app
from agents.contracts.tasks import AgentTaskInput, OrchestratorTaskInput
from agents.core.exceptions import AgentError
from agents.core.logging import configure_agent_logging

logger = structlog.get_logger(__name__)


class _BaseAgentTask(Task):
    """Celery Task base with agent-side logging and failure hooks."""

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        logger.error("celery.task.failed", task_id=task_id, error=str(exc))

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:  # type: ignore[override]
        logger.warning("celery.task.retrying", task_id=task_id, error=str(exc))


@celery_app.task(
    bind=True,
    base=_BaseAgentTask,
    name="agents.bus.tasks.run_orchestration",
    max_retries=2,
    default_retry_delay=5,
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
        # Late import avoids pulling the full LangGraph/Anthropic stack into
        # every process that merely imports celery_app.
        from agents.orchestrator.orchestrator import MasterOrchestrator  # noqa: PLC0415

        orchestrator = MasterOrchestrator()
        result = asyncio.run(orchestrator.run(task_input))
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
    max_retries=1,
    default_retry_delay=10,
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
