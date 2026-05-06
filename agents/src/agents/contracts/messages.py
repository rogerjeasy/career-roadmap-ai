"""JSON-RPC 2.0 message envelope — the A2A wire protocol.

Every agent-to-agent message is wrapped in these envelopes. This makes the
transport format explicit, versionable, and interoperable with any client
that understands JSON-RPC 2.0.

Spec: https://www.jsonrpc.org/specification
"""
from enum import IntEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RpcErrorCode(IntEnum):
    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Application-defined codes (-32000 to -32099)
    AGENT_TIMEOUT = -32000
    AGENT_UNAVAILABLE = -32001
    VALIDATION_FAILED = -32002
    CLARIFICATION_REQUIRED = -32003
    DAG_BUILD_FAILED = -32004


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any | None = None

    model_config = {"frozen": True}


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request envelope for agent task dispatch.

    ``method`` follows the convention ``agent.<agent_type>.<action>``,
    e.g. ``agent.cv_analysis.run``.
    """

    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: str(uuid4()))
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope.

    Exactly one of ``result`` or ``error`` is set; never both.
    """

    jsonrpc: str = "2.0"
    id: str
    result: Any | None = None
    error: JsonRpcError | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None

    model_config = {"frozen": True}
