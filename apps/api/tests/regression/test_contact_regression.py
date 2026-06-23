"""Regression tests for the Contact domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.contact.schemas import ContactRequestCreate
from src.domains.contact.service import ContactService

pytestmark = pytest.mark.regression


async def test_email_owner_key_is_always_lowercased() -> None:
    # REGRESSION: the sender email doubles as the Firestore owner key. It must be
    # normalised to lowercase so "A@x.com" and "a@x.com" map to the same owner.
    repo = MagicMock()
    repo.create = AsyncMock(return_value={"id": "c1"})
    service = ContactService(repo)

    await service.submit(
        ContactRequestCreate(name="A", email="UPPER@Example.Com", message="hi")
    )
    owner = repo.create.call_args.args[0]
    assert owner == owner.lower()
    assert owner == "upper@example.com"
