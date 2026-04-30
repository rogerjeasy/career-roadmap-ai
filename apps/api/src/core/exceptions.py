"""Domain exceptions translated to HTTP responses by middleware."""
from fastapi import status


class AppException(Exception):
    """Base for all application-level errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, detail: str = "Something went wrong"):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"


class AuthorizationError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class ExternalServiceError(AppException):
    """Raised when an MCP server, LLM, or other external service fails."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "upstream_error"