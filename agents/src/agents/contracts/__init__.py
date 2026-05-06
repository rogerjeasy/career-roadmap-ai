"""Public contract types — the ONLY module that API consumers import from agents.

Keeping this surface explicit and minimal is what makes the agents package
a low-coupling dependency. Consumers never reach into agents.core, agents.bus,
or agents.orchestrator directly.
"""
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.messages import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    RpcErrorCode,
)
from agents.contracts.results import AgentResult, AgentResultStatus, OrchestratorResult
from agents.contracts.tasks import (
    AgentTaskInput,
    AgentType,
    OrchestratorTaskInput,
    TaskPriority,
    UserProfileSnapshot,
)

__all__ = [
    # events
    "AgentEvent",
    "AgentEventType",
    # messages
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "RpcErrorCode",
    # results
    "AgentResult",
    "AgentResultStatus",
    "OrchestratorResult",
    # tasks
    "AgentTaskInput",
    "AgentType",
    "OrchestratorTaskInput",
    "TaskPriority",
    "UserProfileSnapshot",
]
