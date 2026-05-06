"""TaskDispatcher — thin facade kept for backward compatibility.

The actual dispatch logic now lives in ``AgentDispatcherNode`` which runs
agents in-process via ``asyncio.gather``. This module re-exports the node
factory so that code that imported ``TaskDispatcher`` continues to work
without changes.
"""
from agents.orchestrator.nodes.agent_dispatcher import (
    AgentDispatcherNode,
    make_agent_dispatcher,
)

TaskDispatcher = AgentDispatcherNode

__all__ = ["TaskDispatcher", "make_agent_dispatcher"]
