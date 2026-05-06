"""AgentRegistry — discovers, registers, and resolves specialist agents.

The Orchestrator only interacts with ``BaseAgent`` via the registry; it
never imports concrete agent classes directly. Agents register themselves
at worker startup, making the system open for extension without modifying
the orchestrator.
"""
import structlog

from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.exceptions import AgentConfigurationError

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """Thread-safe, in-process registry for agent instances.

    One instance lives as the module-level ``registry`` singleton.
    Workers populate it during startup; the orchestrator reads it at runtime.
    """

    def __init__(self) -> None:
        self._agents: dict[AgentType, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent. Raises if the type is already registered."""
        if agent.agent_type in self._agents:
            raise AgentConfigurationError(
                f"Agent '{agent.agent_type.value}' is already registered. "
                "Check for duplicate instantiation.",
                agent_type=agent.agent_type.value,
            )
        self._agents[agent.agent_type] = agent
        logger.info("agent.registered", agent=agent.agent_type.value, name=agent.display_name)

    def get(self, agent_type: AgentType) -> BaseAgent:
        """Return the registered agent or raise ``AgentConfigurationError``."""
        agent = self._agents.get(agent_type)
        if agent is None:
            raise AgentConfigurationError(
                f"No agent registered for '{agent_type.value}'. "
                "Ensure it is registered before the orchestrator starts.",
                agent_type=agent_type.value,
            )
        return agent

    def available(self) -> list[AgentType]:
        """Return all currently registered agent types."""
        return list(self._agents.keys())

    def is_available(self, agent_type: AgentType) -> bool:
        return agent_type in self._agents


# Module-level singleton — imported and populated at worker-process startup.
registry = AgentRegistry()
