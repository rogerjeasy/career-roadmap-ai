"""JSON-RPC 2.0 error codes and response builders for all MCP servers."""
from __future__ import annotations

from enum import IntEnum
from typing import Any


class JsonRpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Application-defined range: -32000 to -32099
    RATE_LIMITED = -32000
    UNAUTHORIZED = -32001
    UPSTREAM_ERROR = -32002
    TOOL_TIMEOUT = -32003
    CACHE_ERROR = -32004


class JsonRpcError(Exception):
    """Raise from tool handlers to produce a well-formed JSON-RPC error response."""

    def __init__(
        self,
        code: JsonRpcErrorCode,
        message: str,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def make_success_response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error_response(
    request_id: str | int | None,
    code: JsonRpcErrorCode,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": int(code), "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
