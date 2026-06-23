"""Unit tests for ContactService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.contact.schemas import ContactRequestAck, ContactRequestCreate
from src.domains.contact.service import ContactService

pytestmark = pytest.mark.unit


def _payload(**over) -> ContactRequestCreate:
    base = {"name": "Ada", "email": "Ada@Example.com", "message": "Hi there"}
    base.update(over)
    return ContactRequestCreate(**base)


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(return_value={"id": "c1"})
    return r


@pytest.fixture
def service(repo: MagicMock) -> ContactService:
    return ContactService(repo)


async def test_submit_returns_ack(service: ContactService) -> None:
    ack = await service.submit(_payload())
    assert isinstance(ack, ContactRequestAck)
    assert ack.received is True


async def test_submit_lowercases_email_as_owner_key(service: ContactService, repo: MagicMock) -> None:
    await service.submit(_payload(email="MixedCase@Example.COM"))
    owner, doc = repo.create.call_args.args
    assert owner == "mixedcase@example.com"
    assert doc["topic"] == "general"


async def test_submit_persists_payload_fields(service: ContactService, repo: MagicMock) -> None:
    await service.submit(_payload(topic="sales", company="Acme"))
    _owner, doc = repo.create.call_args.args
    assert doc["company"] == "Acme"
    assert doc["topic"] == "sales"
