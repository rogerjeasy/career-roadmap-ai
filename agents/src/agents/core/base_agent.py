"""BaseAgent — abstract contract every specialist agent must fulfil.

Specialist agents extend this class and implement ``_execute()``.
``BaseAgent.run()`` wraps the implementation with timing, structured
logging, and error normalisation so that every agent always returns a
well-formed ``AgentResult`` regardless of what happens inside.
"""
import abc
import time

import structlog

from agents.contracts.results import AgentResult, AgentResultStatus
from agents.contracts.tasks import AgentType
from agents.core.context import AgentContext
from agents.core.exceptions import AgentTimeoutError

logger = structlog.get_logger(__name__)


class BaseAgent(abc.ABC):
    """Abstract base for all specialist agents.

    Subclasses must implement:
    - ``agent_type`` property — unique ``AgentType`` enum member
    - ``_execute(context)`` — domain logic; returns a plain dict that
      becomes ``AgentResult.output``

    Subclasses may override:
    - ``display_name`` — human-readable label used in SSE events
    """

    @property
    @abc.abstractmethod
    def agent_type(self) -> AgentType:
        """The agent's unique identifier in the registry."""

    @property
    def display_name(self) -> str:
        return self.agent_type.value.replace("_", " ").title()

    @abc.abstractmethod
    async def _execute(self, context: AgentContext) -> dict:
        """Domain logic. Must return a JSON-serialisable dict."""

    async def run(self, context: AgentContext) -> AgentResult:
        """Public entry-point. Never override — extend ``_execute`` instead."""
        log = logger.bind(
            agent=self.agent_type.value,
            task_id=context.task_id,
            session_id=context.session_id,
            user_id=context.user_id,
            correlation_id=context.correlation_id,
        )
        log.info("agent.started")
        start = time.monotonic()

        try:
            output = await self._execute(context)
            duration_ms = int((time.monotonic() - start) * 1000)
            log.info("agent.completed", duration_ms=duration_ms)
            return AgentResult(
                task_id=context.task_id,
                agent_type=self.agent_type.value,
                status=AgentResultStatus.COMPLETED,
                output=output,
                duration_ms=duration_ms,
            )
        except AgentTimeoutError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("agent.timeout", duration_ms=duration_ms, error=str(exc))
            return AgentResult(
                task_id=context.task_id,
                agent_type=self.agent_type.value,
                status=AgentResultStatus.TIMEOUT,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.error("agent.failed", duration_ms=duration_ms, error=str(exc), exc_info=True)
            return AgentResult(
                task_id=context.task_id,
                agent_type=self.agent_type.value,
                status=AgentResultStatus.FAILED,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
