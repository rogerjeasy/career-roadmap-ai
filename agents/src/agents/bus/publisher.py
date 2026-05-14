"""Type-safe publishers for tasks and events.

``TaskPublisher``  — sends orchestration/agent tasks to Celery.
``EventPublisher`` — emits ``AgentEvent`` objects to Redis pub/sub.

Both are stateless or hold only a Redis connection; they carry no
orchestration logic and have no knowledge of agent internals.
"""
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.bus.celery_app import celery_app
from agents.bus.channel import channel_for_session
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentTaskInput, OrchestratorTaskInput
from agents.core.exceptions import BusPublishError
from agents.core.message_bus import EventPublisherProtocol, TaskPublisherProtocol

logger = structlog.get_logger(__name__)

_ORCHESTRATE_TASK = "agents.bus.tasks.run_orchestration"
_AGENT_TASK = "agents.bus.tasks.run_agent"


class TaskPublisher:
    """Publishes tasks to Celery workers.

    Stateless — safe to instantiate per-request in the API layer.
    Satisfies ``TaskPublisherProtocol``.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def dispatch_orchestration(self, task_input: OrchestratorTaskInput) -> str:
        """Enqueue a top-level orchestration run. Returns the Celery task ID."""
        try:
            async_result = celery_app.send_task(
                _ORCHESTRATE_TASK,
                kwargs={"payload": task_input.model_dump(mode="json")},
                queue="agents.priority",
                task_id=task_input.request_id,
            )
            logger.info(
                "bus.orchestration.dispatched",
                task_id=async_result.id,
                user_id=task_input.user_id,
                session_id=task_input.session_id,
            )
            return async_result.id
        except Exception as exc:
            raise BusPublishError(f"Failed to dispatch orchestration: {exc}") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def dispatch_agent(self, task_input: AgentTaskInput) -> str:
        """Enqueue a single specialist-agent task. Returns the Celery task ID."""
        try:
            async_result = celery_app.send_task(
                _AGENT_TASK,
                kwargs={"payload": task_input.model_dump(mode="json")},
                queue="agents.default",
                task_id=task_input.task_id,
                priority=task_input.priority.value,
            )
            logger.info(
                "bus.agent.dispatched",
                task_id=async_result.id,
                agent_type=task_input.agent_type.value,
                user_id=task_input.user_id,
            )
            return async_result.id
        except Exception as exc:
            raise BusPublishError(f"Failed to dispatch agent task: {exc}") from exc


# Verify this class satisfies the Protocol at import time
assert isinstance(TaskPublisher(), TaskPublisherProtocol)


class EventPublisher:
    """Emits ``AgentEvent`` objects to Redis pub/sub.

    One instance per worker process; holds a synchronous Redis client
    because Celery workers are not async. Satisfies ``EventPublisherProtocol``.

    Events are best-effort: a failure to emit an event is logged but never
    causes the agent task itself to fail.
    """

    def __init__(self, redis_client) -> None:  # type: ignore[no-untyped-def]
        self._redis = redis_client

    # TTL for the event replay list — long enough to survive a slow SSE
    # connection setup, short enough not to waste Redis memory.
    _REPLAY_TTL_SECONDS = 600

    def emit(self, event: AgentEvent) -> None:
        """Publish an event to the session channel. Non-blocking.

        Each event is also appended to a Redis list (``event_log:{channel}``)
        so that a subscriber that connects after events have already been
        published can replay the backlog before switching to live pub/sub.
        """
        channel = channel_for_session(event.user_id, event.session_id)
        try:
            payload = event.model_dump_json()
            list_key = f"event_log:{channel}"
            pipe = self._redis.pipeline()
            # A new orchestration run invalidates all events from the previous
            # run.  Clear the replay list atomically before appending so a
            # subscriber that connects mid-run never replays stale terminal
            # events and redirects the user prematurely.
            if event.event_type is AgentEventType.ORCHESTRATION_STARTED:
                pipe.delete(list_key)
            pipe.rpush(list_key, payload)
            pipe.expire(list_key, self._REPLAY_TTL_SECONDS)
            pipe.publish(channel, payload)
            pipe.execute()
            logger.debug(
                "bus.event.emitted",
                event_type=event.event_type.value,
                channel=channel,
                event_id=event.event_id,
            )
        except Exception as exc:
            logger.warning(
                "bus.event.emit_failed",
                channel=channel,
                event_type=event.event_type.value,
                error=str(exc),
            )


assert isinstance(EventPublisher(None), EventPublisherProtocol)  # type: ignore[arg-type]
