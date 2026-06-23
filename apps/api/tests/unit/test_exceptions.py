"""Unit tests for the domain exception hierarchy (``src.core.exceptions``).

The global handler in ``src.main`` reads ``status_code``/``error_code``/``detail``
off these exceptions, so those three attributes form a public contract.
"""
import pytest
from fastapi import status

from src.core.exceptions import (
    AppException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

pytestmark = pytest.mark.unit


def test_base_defaults() -> None:
    exc = AppException()
    assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc.error_code == "internal_error"
    assert exc.detail == "Something went wrong"
    assert str(exc) == "Something went wrong"


def test_custom_detail_is_preserved() -> None:
    exc = NotFoundError("roadmap r1 not found")
    assert exc.detail == "roadmap r1 not found"
    assert str(exc) == "roadmap r1 not found"


@pytest.mark.parametrize(
    ("exc_cls", "code", "error_code"),
    [
        (NotFoundError, status.HTTP_404_NOT_FOUND, "not_found"),
        (ValidationError, status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error"),
        (AuthenticationError, status.HTTP_401_UNAUTHORIZED, "authentication_failed"),
        (AuthorizationError, status.HTTP_403_FORBIDDEN, "forbidden"),
        (ConflictError, status.HTTP_409_CONFLICT, "conflict"),
        (ExternalServiceError, status.HTTP_502_BAD_GATEWAY, "upstream_error"),
        (ServiceUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable"),
    ],
)
def test_status_and_error_codes(exc_cls: type[AppException], code: int, error_code: str) -> None:
    exc = exc_cls("boom")
    assert exc.status_code == code
    assert exc.error_code == error_code


def test_all_domain_exceptions_subclass_appexception() -> None:
    for exc_cls in (
        NotFoundError,
        ValidationError,
        AuthenticationError,
        AuthorizationError,
        ConflictError,
        ExternalServiceError,
        ServiceUnavailableError,
    ):
        assert issubclass(exc_cls, AppException)


def test_can_be_raised_and_caught_as_base() -> None:
    with pytest.raises(AppException):
        raise ConflictError("dup")
